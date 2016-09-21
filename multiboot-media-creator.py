#!/usr/bin/python
# This is a reimimplemtation of the MultiImage-Media-Creator in Python.
# Initial work on the bash version of this was done by Dave Riches, Bob Jensen
# and Dennis Johnson
#
# Copyright (C) 2011 Tom Callaway <spot@fedoraproject.org>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.
#
# Inspiration and implementation ideas borrowed from fedpkg by Jesse Keating
# which is also available under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the License,
# or (at your option) any later version.

import argparse
import glob
import locale
import os
import re
import shutil
import subprocess
import sys
import time

name = 'Multiboot Media Creator'
version = 0.8
my_description = '{0} {1}'.format(name, version)

def makeuefidirs(imagedir, verbose):
    uefi_dirs = ['EFI/BOOT', 'EFI/BOOT/fonts', 'images']
    for dir in uefi_dirs:
        if os.path.isdir(os.path.join(imagedir, dir)):
            # The directory exists, do nothing.
            if verbose:
               print '{0} exists, skipping directory creation.'.format(os.path.join(imagedir, dir))
        else:
            if verbose:
                print 'Creating directory: {0}'.format(os.path.join(imagedir, dir))
            try:
                os.makedirs(os.path.join(imagedir, dir))
            except:
                error = sys.exc_info()[1]
                sys.exit('I was trying to make a UEFI directory as {0}, but I failed with error {1}. Exiting.'.format(os.makedirs(os.path.join(imagedir, dir)), error))

def makehelperdirs(imagedir, iso_basename, type, verbose):
    if type == "grub":
        dirs = ['boot', 'images', 'CHECKSUM']
    else:
        dirs = ['isolinux', 'images']
    for dir in dirs:
        if os.path.isdir(os.path.join(imagedir, iso_basename, dir)):
            # The directory exists, do nothing.
            if verbose:
                print '{0} exists, skipping directory creation.'.format(os.path.join(imagedir, iso_basename, dir))
        else:
            if verbose:
                print 'Creating directory: {0}'.format(os.path.join(imagedir, iso_basename, dir))
            try:
                os.makedirs(os.path.join(imagedir, iso_basename, dir))
            except:
                error = sys.exc_info()[1]
                sys.exit('I was trying to make an image directory as {0}, but I failed with error {1}. Exiting.'.format(os.makedirs(os.path.join(imagedir, iso_basename, dir)), error))

def makeisolinuximage(isolist, imagedir, mountdir, timeout, bootdefaultiso, targetiso, targetname, isolinuxsplash, isodir, nomultiarch, efi, bootdefaultnum, verbose, volumeheaderinfo):
    # Second Sanity Check
    # Memtest86+ test
    memtest_list = glob.glob('/boot/memtest86+-*')
    if memtest_list:
        memtest_binary = memtest_list[0]
    else:
        sys.exit('Could not find memtest86+ binary in /boot ? Perhaps memtest86+ is not installed?')

    if efi:
       uefidir = os.path.join(imagedir, 'EFI/BOOT')
       ueficonf = os.path.join(uefidir, 'grub.cfg')
       if verbose:
           print 'Making the EFI directories for grub2 in IMAGEDIR: {0}'.format(uefidir)
       makeuefidirs(imagedir, verbose)
       if verbose:
           print 'Copying the needed EFI helper files in IMAGEDIR: {0}'.format(uefidir)
       shutil.copy2('/boot/efi/EFI/fedora/shim.efi', os.path.join(uefidir, 'BOOTX64.efi'))
       shutil.copy2('/boot/efi/EFI/fedora/MokManager.efi', uefidir)
       shutil.copy2('/boot/efi/EFI/fedora/gcdx64.efi', os.path.join(uefidir, 'grubx64.efi'))
       shutil.copy2('/boot/efi/EFI/fedora/fonts/unicode.pf2', os.path.join(uefidir, 'fonts'))

       # Open our master GRUB2 config file.
       masterueficonf = open(ueficonf, 'w')

       # Write our header into the master GRUB2 config file
       # There is almost certainly a more appropriate way to do this.
       #masterueficonf.write('\n')
       masterueficonf.write('set default="{0}"\n'.format(bootdefaultnum))
       masterueficonf.write('\n')
       masterueficonf.write('function load_video {\n')
       masterueficonf.write('  insmod efi_gop\n')
       masterueficonf.write('  insmod efi_uga\n')
       masterueficonf.write('  insmod video_bochs\n')
       masterueficonf.write('  insmod video_cirrus\n')
       masterueficonf.write('  insmod all_video\n')
       masterueficonf.write('}\n')
       masterueficonf.write('\n')
       masterueficonf.write('load_video\n')
       masterueficonf.write('set gfxpayload=keep\n')
       masterueficonf.write('insmod gzio\n')
       masterueficonf.write('insmod part_gpt\n')
       masterueficonf.write('insmod ext2\n')
       masterueficonf.write('\n')
       masterueficonf.write('set timeout={0}\n'.format(timeout))
       masterueficonf.write('### END /etc/grub.d/00_header ###\n')
       masterueficonf.write('\n')
       masterueficonf.write('search --no-floppy --set=root -l \'{0}\'\n'.format(targetname))
       masterueficonf.write('\n')
       masterueficonf.write('## BEGIN /etc/grub.d/10_linux ###\n')

    # If the nomultiarch flag is set to true, disable multiarch. Otherwise, enable multiarch.
    if nomultiarch:
       multiarch = False
    else:
       multiarch = True

    # In the specific case where we have a valid multiarch pair target, and we set it as the default, we don't want to set the individual
    # item as default. In all other cases, we do. So we use this variable to track it.
    pairedtarget_is_default = False

    # Make the isolinux directory
    isolinuxdir = os.path.join(imagedir, 'isolinux')
    isolinuxconf = os.path.join(isolinuxdir, 'isolinux.cfg')
    if verbose:
        print 'Making the directory for isolinux in IMAGEDIR: {0}'.format(isolinuxdir)
    try:
        os.makedirs(isolinuxdir)
    except:
        error = sys.exc_info()[1]
        sys.exit('I was trying to make the isolinux directory as {0}, but I failed with error {1}. Exiting.'.format(isolinuxdir, error))
    # Handle splash image
    isolinuxsplash_basename = os.path.basename(isolinuxsplash)
    if verbose:
       print 'Copying {0} splash file to {1}.'.format(isolinuxsplash, isolinuxdir)
    shutil.copy2(isolinuxsplash, isolinuxdir)

    # Copy memtest86+ binary over
    if verbose:
	print 'Copying {0} memtest86+ kernel to {1}.'.format(memtest_binary, os.path.join(isolinuxdir, 'memtest'))
    shutil.copy2(memtest_binary, os.path.join(isolinuxdir, 'memtest'))

    # Open our master config file.
    masterconf = open(isolinuxconf, 'w')

    # Write our header into the master config file
    # TODO: This is based on the Fedora 14 header, probably needs to be cleaned up.

    masterconf.write('default vesamenu.c32\n')
    masterconf.write('timeout {0}\n'.format(timeout*10))
    masterconf.write('\n')
    # masterconf.write('display boot.msg\n')
    # masterconf.write('\n')
    masterconf.write('menu background {0}\n'.format(isolinuxsplash_basename))
    masterconf.write('menu title Welcome to {0}\n'.format(targetname))
    # TODO: Configurable color codes?
    masterconf.write('menu color border 0 #ffffffff #00000000\n')
    masterconf.write('menu color sel 7 #ffffffff #ff000000\n')
    masterconf.write('menu color title 0 #ffffffff #00000000\n')
    masterconf.write('menu color tabmsg 0 #ffffffff #00000000\n')
    masterconf.write('menu color unsel 0 #ffffffff #00000000\n')
    masterconf.write('menu color hotsel 0 #ff000000 #ffffffff\n')
    masterconf.write('menu color hotkey 7 #ffffffff #ff000000\n')
    masterconf.write('menu color scrollbar 0 #ffffffff #00000000\n')
    masterconf.write('\n')

    # If multiarch mode is enabled, we need two (maybe three) files.
    if multiarch:
       # This file is where we store the normal 32bit target entries
       f32file = os.path.join(imagedir, 'normal32targets.part')
       f32 = open(f32file, 'w')
       f32.write('menu begin\n')
       f32.write('menu title i386\n')

       # This file is where we store the normal 64bit target entries
       f64file = os.path.join(imagedir, 'normal64targets.part')
       f64 = open(f64file, 'w')
       f64.write('menu begin\n')
       f64.write('menu title x86_64\n')

       # This file is where we put any unpaired entries
       fnopairentries = False
       fnopairfile = os.path.join(imagedir, 'normalnopairtargets.part')
       fnopair = open(fnopairfile, 'w')

    else:
       # This file is where we store all normal target entries
       ffile = os.path.join(imagedir, 'normaltargets.part')
       f = open(ffile, 'w')

    # This file is where we store the isolinux config bits for Live Images
    bvtfile = os.path.join(imagedir, 'basicvideotargets.part')
    bvt = open(bvtfile, 'w')
    bvt.write('menu begin\n')
    bvt.write('menu title Boot (Basic Video)\n')
    bvt.write('\n')

    # This file is where we store any multiarch targets
    # If we're not in multiarch mode, or we don't find any multiarch targets,
    # this file will be empty.
    multiarchentries = False
    matfile = os.path.join(imagedir, 'multiarchtargets.part')
    mat = open(matfile, 'w')

    for (counter, iso) in enumerate(isolist):
        basename = os.path.basename(iso)
        iso_basename = os.path.splitext(basename)[0]
        pretty_iso_basename = re.sub(r'-', ' ', iso_basename)

        # Are we in multiarch mode?
        if multiarch:
            if verbose:
                print 'Multiarch mode enabled. Checking {0} to to see if it matches i[3456]+86'.format(iso)
            # Okay we are. Lets see if this string is i*86.
            ia32_pattern = re.compile('i[3456]+86')
            if ia32_pattern.search(iso):
                if verbose:
                    print '{0} matches the i[3456]+86 pattern, looking for the x86_64 partner...'.format(iso)
                # Hey, it matches! Lets make the x86_64 iso name.
                x86_64_iso = ia32_pattern.sub('x86_64', iso)
                # Now, we check for it in the list of isos
                if isolist.count(x86_64_iso):
                    # Found it
                    if verbose:
                        print 'Found {0} partner iso for {1}!. Writing out multiarch entry for the pair.'.format(x86_64_iso, iso)
                    pairfound = True
		    multiarchentries = True
                else:
                    # Did not find it. :(
                    if verbose:
                        print 'Could not find {0} partner iso for {1}. Going to write out a non-multiarch entry for {1}.'.format(x86_64_iso, iso)
                    pairfound = False
            else:
                if verbose:
                   print '{0} did not match  i[3456]+86'.format(iso)
                # If it isn't i[3456]+86, then it has no pair.
                pairfound = False
	else:
            if verbose:
                print 'Multiarch mode disabled.'
	    # pairfound is always false when multiarch is disabled
	    pairfound = False

        # Now, we need to loopback mount this ISO.
        if verbose:
            print 'Loopback mounting {0} on {1}'.format(iso, mountdir)
        mount_command = 'mount -o loop "{0}" "{1}"'.format(iso, mountdir)
        result = os.system(mount_command)
        if result:
            sys.exit('I tried to run {0}, but it failed. Exiting.'.format(mount_command))
        # We used to check for "live" in the isolinux/isolinux.cfg, but all Fedora ISOs now
        # pass that check, including the install media! Now, we just look for .discinfo. If it
        # is present, we know we're not on a live ISO.
        discinfo_file = os.path.join(mountdir, '.discinfo')
        if os.path.isfile(discinfo_file):
            if verbose:
                print '{0} found. Must be an InstallISO.'.format(discinfo_file)
            iso_type_live = False
        else:
            if verbose:
                print '{0} _NOT_ found. Must be a LiveISO.'.format(discinfo_file)
            iso_type_live = True

        if iso_type_live:
            # Okay, this is a Live ISO.
            if verbose:
                print '{0} is a Live ISO. Copying files to {1}.'.format(iso, os.path.join(imagedir, iso_basename))
            shutil.copytree(mountdir, os.path.join(imagedir, iso_basename))

            # HACK HACK HACK
            # We're copying the first efiboot.img and macboot.img we find.
            if efi:
               if os.path.isfile(os.path.join(imagedir, 'images/efiboot.img')):
                   if verbose:
                       print '{0} already present, nothing to do here.'.format(os.path.join(imagedir, 'images/efiboot.img'))
               else:
                   if os.path.isfile(os.path.join(mountdir, 'images/efiboot.img')):
                       if verbose:
                           print 'Copying {0} to {1}.'.format(os.path.join(mountdir, 'images/efiboot.img'), os.path.join(imagedir, 'images/efiboot.img'))
                       shutil.copy2(os.path.join(mountdir, 'images/efiboot.img'), os.path.join(imagedir, 'images/efiboot.img'))
               if os.path.isfile(os.path.join(imagedir, 'images/macboot.img')):
                   if verbose:
                       print '{0} already present, nothing to do here.'.format(os.path.join(imagedir, 'images/macboot.img'))
               else:
                   if os.path.isfile(os.path.join(mountdir, 'images/macboot.img')):
                       if verbose:
                           print 'Copying {0} to {1}.'.format(os.path.join(mountdir, 'images/macboot.img'), os.path.join(imagedir, 'images/macboot.img'))
               	       shutil.copy2(os.path.join(mountdir, 'images/macboot.img'), os.path.join(imagedir, 'images/macboot.img'))

            if pairfound:
                x86_64_basename = os.path.basename(x86_64_iso)
                x86_64_iso_basename = os.path.splitext(x86_64_basename)[0]

                pairname = re.sub(r'i[3456]+86-', '', iso_basename)
                pretty_pairname = re.sub(r'-', ' ', pairname)
		mat.write('label {0}\n'.format(pairname))
                mat.write('  menu label Boot {0}\n'.format(pretty_pairname))
                mat.write('  kernel ifcpu64.c32\n')
                if bootdefaultiso == iso:
                    mat.write('  menu default\n')
                if bootdefaultiso == x86_64_iso:
                    mat.write('  menu default\n')
                mat.write('  append {0} -- {1}\n'.format(x86_64_iso_basename, iso_basename))
                mat.write('\n')

	        # Write out non-multiboot items
                if verbose:
                    print 'Writing ISO specific entry for {0} and {1} into isolinux configs.'.format(iso_basename, x86_64_iso_basename)

            # If multiarch is enabled
            if multiarch:
                # And we found a pair, then write out to the split files, and pop the x86_64 item off the list.
                if pairfound:
                    f32.write('label {0}\n'.format(iso_basename))
                    f32.write('  menu label Boot {0}\n'.format(pretty_iso_basename))
                    # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
                    f32.write('  kernel /{0}/isolinux/vmlinuz\n'.format(iso_basename))
                    f32.write('  append initrd=/{0}/isolinux/initrd.img root=live:CDLABEL={1} rd.live.dir=/{2}/LiveOS/ rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0\n'.format(iso_basename, targetname, iso_basename))
                    f32.write('\n')

                    if verbose:
                        print 'Unmounting {0}, and mounting {1} to copy second half of pair to {2}.'.format(iso, x86_64_iso, os.path.join(imagedir, x86_64_iso_basename))
                    unmount_command = 'umount "{0}"'.format(mountdir)
                    if verbose:
                        print 'Sleeping for 3 seconds here, otherwise we might try to umount while GNOME is still looking at it.'
                    time.sleep(3)
                    result = os.system(unmount_command)
                    if result:
                        sys.exit('I tried to run {0}, but it failed. Exiting.'.format(unmount_command))
                    mount_command = 'mount -o loop "{0}" "{1}"'.format(x86_64_iso, mountdir)
                    result = os.system(mount_command)
                    if result:
                        sys.exit('I tried to run {0}, but it failed. Exiting.'.format(mount_command))
                    shutil.copytree(mountdir, os.path.join(imagedir, x86_64_iso_basename))

                    # HACK HACK HACK
                    # We're copying the first efiboot.img and macboot.img we find.
                    if efi:
                        if os.path.isfile(os.path.join(imagedir, 'images/efiboot.img')):
                            if verbose:
                                print '{0} already present, nothing to do here.'.format(os.path.join(imagedir, 'images/efiboot.img'))
                        else:
                            if os.path.isfile(os.path.join(mountdir, 'images/efiboot.img')):
                                if verbose:
                                    print 'Copying {0} to {1}.'.format(os.path.join(mountdir, 'images/efiboot.img'), os.path.join(imagedir, 'images/efiboot.img'))
                            shutil.copy2(os.path.join(mountdir, 'images/efiboot.img'), os.path.join(imagedir, 'images/efiboot.img'))
                        if os.path.isfile(os.path.join(imagedir, 'images/macboot.img')):
                            if verbose:
                                print '{0} already present, nothing to do here.'.format(os.path.join(imagedir, 'images/macboot.img'))
                        else:
                            if os.path.isfile(os.path.join(mountdir, 'images/macboot.img')):
                                if verbose:
                                    print 'Copying {0} to {1}.'.format(os.path.join(mountdir, 'images/macboot.img'), os.path.join(imagedir, 'images/macboot.img'))
                            shutil.copy2(os.path.join(mountdir, 'images/macboot.img'), os.path.join(imagedir, 'images/macboot.img'))

                    pretty_x86_64_iso_basename = re.sub(r'-', ' ', x86_64_iso_basename)

                    f64.write('label {0}\n'.format(x86_64_iso_basename))
                    f64.write('  menu label Boot {0}\n'.format(pretty_x86_64_iso_basename))
                    # Note that we only need the x86_64_iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use x86_64_iso_basename.
                    f64.write('  kernel /{0}/isolinux/vmlinuz\n'.format(x86_64_iso_basename))
                    f64.write('  append initrd=/{0}/isolinux/initrd.img root=live:CDLABEL={1} rd.live.dir=/{2}/LiveOS/ rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0\n'.format(x86_64_iso_basename, targetname, x86_64_iso_basename))
                    f64.write('\n')

                    # Only write out x86_64 targets to the GRUB2 EFI config (no support for 32bit EFI)
                    if efi:
                        masterueficonf.write('menuentry \'{0}\' --class fedora --class gnu-linux --class gnu --class os {{\n'.format(pretty_x86_64_iso_basename))
                        masterueficonf.write('\tlinuxefi /{0}/isolinux/vmlinuz root=live:LABEL={1} rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0 rd.live.dir=/{2}/LiveOS/\n'.format(x86_64_iso_basename, targetname, x86_64_iso_basename))
                        masterueficonf.write('\tinitrdefi /{0}/isolinux/initrd.img\n'.format(x86_64_iso_basename))
                        masterueficonf.write('}\n')

                    # Now, pull x86_64_iso out of 'isolist'
                    try:
                        isolist.remove(x86_64_iso)
                    except:
                        sys.exit('Tried to remove {0} from the isolist, but I failed. Exiting.'.format(x86_64_iso))

                # ... but we didn't find a pair, then write to the nopairfile (and indicate that we needed to)
                else:
                    fnopairentries = True
                    fnopair.write('label {0}\n'.format(iso_basename))
                    fnopair.write('  menu label Boot {0}\n'.format(pretty_iso_basename))
                    if bootdefaultiso == iso:
                        fnopair.write('  menu default\n')
                    # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
                    fnopair.write('  kernel /{0}/isolinux/vmlinuz\n'.format(iso_basename))
                    fnopair.write('  append initrd=/{0}/isolinux/initrd.img root=live:CDLABEL={1} rd.live.dir=/{2}/LiveOS/ rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0\n'.format(iso_basename, targetname, iso_basename))
                    fnopair.write('\n')

                    if efi:
                        masterueficonf.write('menuentry \'{0}\' --class fedora --class gnu-linux --class gnu --class os {{\n'.format(pretty_iso_basename))
                        masterueficonf.write('\tlinuxefi /{0}/isolinux/vmlinuz root=live:LABEL={1} rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0 rd.live.dir=/{2}/LiveOS/\n'.format(iso_basename, targetname, iso_basename))
                        masterueficonf.write('\tinitrdefi /{0}/isolinux/initrd.img\n'.format(iso_basename))
                        masterueficonf.write('}\n')

            # Multiarch disabled
            else:
                f.write('label {0}\n'.format(iso_basename))
                f.write('  menu label Boot {0}\n'.format(pretty_iso_basename))
                if bootdefaultiso == iso:
                    f.write('  menu default\n')
                # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
                f.write('  kernel /{0}/isolinux/vmlinuz\n'.format(iso_basename))
                f.write('  append initrd=/{0}/isolinux/initrd.img root=live:CDLABEL={1} rd.live.dir=/{2}/LiveOS/ rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0\n'.format(iso_basename, targetname, iso_basename))
                f.write('\n')

                if efi:
                    masterueficonf.write('menuentry \'{0}\' --class fedora --class gnu-linux --class gnu --class os {{\n'.format(pretty_iso_basename))
                    masterueficonf.write('\tlinuxefi /{0}/isolinux/vmlinuz root=live:LABEL={1} rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0 rd.live.dir=/{2}/LiveOS/\n'.format(iso_basename, targetname, iso_basename))
                    masterueficonf.write('\tinitrdefi /{0}/isolinux/initrd.img\n'.format(iso_basename))
                    masterueficonf.write('}\n')

            # Now, we write out the basic video entry
            bvt.write('label {0}_basicvideo\n'.format(iso_basename))
            bvt.write('  menu label {0} (Basic Video)\n'.format(pretty_iso_basename))
            if bootdefaultiso == iso:
                bvt.write('  menu default\n')
            # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
            bvt.write('  kernel /{0}/isolinux/vmlinuz\n'.format(iso_basename))
            bvt.write('  append initrd=/{0}/isolinux/initrd.img root=live:CDLABEL={1} rd.live.dir=/{2}/LiveOS/ rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0 xdriver=vesa nomodeset\n'.format(iso_basename, targetname, iso_basename))
            bvt.write('\n')

            if pairfound:
                # Write out the basic Video Entry for x86_64 too.
                bvt.write('label {0}_basicvideo\n'.format(x86_64_iso_basename))
                bvt.write('  menu label {0} (Basic Video)\n'.format(pretty_x86_64_iso_basename))
                if bootdefaultiso == x86_64_iso:
                    bvt.write('  menu default\n')
                # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
                bvt.write('  kernel /{0}/isolinux/vmlinuz\n'.format(x86_64_iso_basename))
                bvt.write('  append initrd=/{0}/isolinux/initrd.img root=live:CDLABEL={1} rd.live.dir=/{2}/LiveOS/ rootfstype=auto ro rd.live.image quiet rhgb rd.luks=0 rd.md=0 rd.dm=0 xdriver=vesa nomodeset\n'.format(x86_64_iso_basename, targetname, x86_64_iso_basename))
                bvt.write('\n')

            makehelperdirs(imagedir, iso_basename, "isolinux", verbose)

        else:
            # Not a Live ISO.
            if verbose:
                print '{0} is NOT a Live ISO. Copying files to {1}.'.format(iso, os.path.join(imagedir, iso_basename))
            makehelperdirs(imagedir, iso_basename, "isolinux", verbose)
            shutil.copy2(os.path.join(mountdir, 'isolinux/vmlinuz'), os.path.join(imagedir, iso_basename, 'isolinux/vmlinuz'))
            shutil.copy2(os.path.join(mountdir, 'isolinux/initrd.img'), os.path.join(imagedir, iso_basename, 'isolinux/initrd.img'))
            if os.path.isfile(os.path.join(mountdir, 'images/install.img')):
                shutil.copy2(os.path.join(mountdir, 'images/install.img'), os.path.join(imagedir, iso_basename, 'images/install.img'))

            if pairfound:
                x86_64_basename = os.path.basename(x86_64_iso)
                x86_64_iso_basename = os.path.splitext(x86_64_basename)[0]

                pairname = re.sub(r'i[3456]+86-', '', iso_basename)
                pretty_pairname = re.sub(r'-', ' ', pairname)
                mat.write('label {0}\n'.format(pairname))
                mat.write('  menu label Install {0}\n'.format(pretty_pairname))
                mat.write('  kernel ifcpu64.c32\n')
                if bootdefaultiso == iso:
                    mat.write('  menu default\n')
                if bootdefaultiso == x86_64_iso:
                    mat.write('  menu default\n')
                mat.write('  append {0} -- {1}\n'.format(x86_64_iso_basename, iso_basename))
                mat.write('\n')

            # If multiarch is enabled
            if multiarch:
                # And we found a pair, then write out to the split files, and pop the x86_64 item off the list.
                if pairfound:
                    f32.write('label {0}\n'.format(iso_basename))
                    f32.write('  menu label Install {0}\n'.format(pretty_iso_basename))
                    # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
                    f32.write('  kernel /{0}/isolinux/vmlinuz\n'.format(iso_basename))
                    f32.write('  append initrd=/{0}/isolinux/initrd.img repo=hd:LABEL={1}:/{2}/\n'.format(iso_basename, targetname, iso_basename))
                    f32.write('\n')

                    if verbose:
                        print 'Copying second half of iso pair to {1}.'.format(x86_64_iso, os.path.join(imagedir, x86_64_iso_basename))
                    unmount_command = 'umount "{0}"'.format(mountdir)
                    if verbose:
                        print 'Sleeping for 3 seconds here, otherwise we might try to umount while GNOME is still looking at it.'
                    time.sleep(3)
                    result = os.system(unmount_command)
                    if result:
                        sys.exit('I tried to run {0}, but it failed. Exiting.'.format(unmount_command))
                    mount_command = 'mount -o loop "{0}" "{1}"'.format(x86_64_iso, mountdir)
                    result = os.system(mount_command)
                    if result:
                        sys.exit('I tried to run {0}, but it failed. Exiting.'.format(mount_command))
                    makehelperdirs(imagedir, x86_64_iso_basename, "isolinux", verbose)
                    shutil.copy2(os.path.join(mountdir, 'isolinux/vmlinuz'), os.path.join(imagedir, x86_64_iso_basename, 'isolinux/vmlinuz'))
                    shutil.copy2(os.path.join(mountdir, 'isolinux/initrd.img'), os.path.join(imagedir, x86_64_iso_basename, 'isolinux/initrd.img'))
                    if os.path.isfile(os.path.join(mountdir, 'images/install.img')):
                        shutil.copy2(os.path.join(mountdir, 'images/install.img'), os.path.join(imagedir, x86_64_iso_basename, 'images/install.img'))

                    pretty_x86_64_iso_basename = re.sub(r'-', ' ', x86_64_iso_basename)
                    # isolinux can't read directories or files longer than 31 characters.
                    # Truncate if we need to. (Yes, this could cause issues. :P)
                    if len(x86_64_iso_basename) > 31:
                        x86_64_iso_basename = x86_64_iso_basename[:31]
                        if verbose:
                            print '{0} is {1}, this is longer than the isolinux 31 character max.'.format(x86_64_iso_basename, len(x86_64_iso_basename))
                            print 'In the isolinux.cfg, we will refer to it as {0}.'.format(x86_64_iso_basename)
                    else:
                        x86_64_iso_basename = x86_64_iso_basename

                    f64.write('label {0}\n'.format(x86_64_iso_basename))
                    f64.write('  menu label Install {0}\n'.format(pretty_x86_64_iso_basename))
                    # Note that we only need the x86_64_iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use x86_64_iso_basename.
                    f64.write('  kernel /{0}/isolinux/vmlinuz\n'.format(x86_64_iso_basename))
                    f64.write('  append initrd=/{0}/isolinux/initrd.img repo=hd:LABEL={1}:/{2}/\n'.format(x86_64_iso_basename, targetname, x86_64_iso_basename))
                    f64.write('\n')
                    # Now, pull x86_64_iso out of 'isolist'
                    try:
                        isolist.remove(x86_64_iso)
                    except:
                        sys.exit('Tried to remove {0} from the isolist, but I failed. Exiting.'.format(x86_64_iso))

                # ... but we didn't find a pair, then write to the nopairfile (and indicate that we needed to)
                else:
                    fnopairentries = True
                    fnopair.write('label {0}\n'.format(iso_basename))
                    fnopair.write('  menu label Install {0}\n'.format(pretty_iso_basename))
                    if bootdefaultiso == iso:
                        fnopair.write('  menu default\n')
                    # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
                    fnopair.write('  kernel /{0}/isolinux/vmlinuz\n'.format(iso_basename))
                    fnopair.write('  append initrd=/{0}/isolinux/initrd.img repo=hd:LABEL={1}:/{2}/\n'.format(iso_basename, targetname, iso_basename))
                    fnopair.write('\n')

            # Multiarch disabled
            else:
                f.write('label {0}\n'.format(iso_basename))
                f.write('  menu label Install {0}\n'.format(pretty_iso_basename))
                if bootdefaultiso == iso:
                    f.write('  menu default\n')
                f.write('  kernel /{0}/isolinux/vmlinuz\n'.format(iso_basename))
                # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
                f.write('  append initrd=/{0}/isolinux/initrd.img repo=hd:LABEL={1}:/{2}/\n'.format(iso_basename, targetname, iso_basename))
                f.write('\n')

            # Now, we write out the basic video entry
            bvt.write('label {0}_basicvideo\n'.format(iso_basename))
            bvt.write('  menu label {0} (Basic Video)\n'.format(pretty_iso_basename))
            if bootdefaultiso == iso:
                bvt.write('  menu default\n')
            # Note that we only need the iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
            bvt.write('  kernel /{0}/isolinux/vmlinuz\n'.format(iso_basename))
            bvt.write('  append initrd=/{0}/isolinux/initrd.img repo=hd:LABEL={1}:/{2} xdriver=vesa nomodeset\n'.format(iso_basename, targetname, iso_basename))
            bvt.write('\n')

            if pairfound:
                # Write out the basic Video Entry for x86_64 too.
                bvt.write('label {0}_basicvideo\n'.format(x86_64_iso_basename))
                bvt.write('  menu label {0} (Basic Video)\n'.format(pretty_x86_64_iso_basename))
                if bootdefaultiso == x86_64_iso:
                    bvt.write('  menu default\n')
                # Note that we only need the x86_64_iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use x86_64_iso_basename.
                bvt.write('  kernel /{0}/isolinux/vmlinuz\n'.format(x86_64_iso_basename))
                bvt.write('  append initrd=/{0}/isolinux/initrd.img repo=hd:LABEL={1}:/{2} xdriver=vesa nomodeset\n'.format(x86_64_iso_basename, targetname, x86_64_iso_basename))
                bvt.write('\n')

            if verbose:
                print 'Copying {0} into {1}.'.format(iso, os.path.join(imagedir, iso_basename))
            shutil.copy2(iso, os.path.join(imagedir, iso_basename))

            if pairfound:
                if verbose:
                     print 'Copying {0} into {1}.'.format(x86_64_iso, os.path.join(imagedir, x86_64_iso_basename))
                shutil.copy2(x86_64_iso, os.path.join(imagedir, x86_64_iso_basename))

        # Unmount the iso
        unmount_command = 'umount "{0}"'.format(mountdir)
        result = os.system(unmount_command)
        if result:
            sys.exit('I tried to run {0}, but it failed. Exiting.'.format(unmount_command))

    # We're now done writing to the multiboot config
    mat.close()

    # We don't need any other changes to fnopair, close it.
    if multiarch:
        fnopair.close()

    # Close out the multiarch config menus and close them, if in multiarch mode.
    if multiarch and multiarchentries:
        f32.write('menu separator\n')
        f32.write('\n')
        f32.write('label return\n')
        f32.write('menu label Return to architecture menu...\n')
        f32.write('         menu exit\n')
        f32.write('\n')
        f32.write('menu end\n')
        f32.write('\n')
        f32.close()
        f64.write('menu separator\n')
        f64.write('\n')
        f64.write('label return\n')
        f64.write('menu label Return to architecture menu...\n')
        f64.write('         menu exit\n')
        f64.write('\n')
        f64.write('menu end\n')
        f64.write('\n')
        f64.close()

    # Now, we need to append mat to the master config file
    # But only if we found some multiarch entries
    if multiarchentries:
        masterconf.write(open(matfile).read())

    # Next, we need to merge in any unpaired entries found in multiarch mode
    if fnopairentries:
        masterconf.write(open(fnopairfile).read())



    # Now, write out the Select Architecture menu.
    # We use the f32 and f64 entries.
    if multiarch and multiarchentries:
        # Add the separator in the master config
        masterconf.write('menu separator\n')
        masterconf.write('\n')

        masterconf.write('menu begin\n')
        masterconf.write('menu title Select Specific Architecture\n')
        masterconf.write('\n')
        masterconf.write(open(f32file).read())
        masterconf.write(open(f64file).read())
        masterconf.write('menu separator\n')
        masterconf.write('\n')
        masterconf.write('label return\n')
        masterconf.write('         menu label Return to main menu...\n')
        masterconf.write('         menu exit\n')
        masterconf.write('\n')
        masterconf.write('menu end\n')
    else:
        if multiarch:
            # Getting here means we are in multiarch mode but we found no valid pairs. Do nothing.
            if verbose:
                print 'You enabled multiarch mode, but there were no valid multiarch pairs... maybe you did something wrong?'
        else:
            # Getting here means we're not in multiarch mode, so we just write out normal entries from ffile.
            masterconf.write(open(ffile).read())
            # Add the separator in the master config
            masterconf.write('menu separator\n')
            masterconf.write('\n')

    # End the "loose" entries menu in the master config
    masterconf.write('menu end\n')
    masterconf.write('\n')

    # Write the footer for the menus in bvt
    bvt.write('menu separator\n')
    bvt.write('\n')
    bvt.write('label return\n')
    bvt.write(' 	menu label Return to main menu...\n')
    bvt.write(' 	menu exit\n')
    bvt.write('\n')
    bvt.write('menu end\n')

    # We are now done writing to bvt
    bvt.close()

    # We will always have bvt entries, so write them to the master file now.
    masterconf.write(open(bvtfile).read())

    # At this point, we no longer need matfile or bvtfile, and we don't want them written on the image
    os.remove(matfile)
    os.remove(bvtfile)

    # Same thing is true for the multiarch files (or the non multiarch ffile).
    if multiarch:
        os.remove(f32file)
        os.remove(f64file)
        os.remove(fnopairfile)
    else:
        os.remove(ffile)

    # Here's our master footer.
    masterconf.write('\n')
    masterconf.write('label memtest\n')
    masterconf.write('  menu label Memory Test\n')
    masterconf.write('  kernel memtest\n')
    masterconf.write('\n')
    masterconf.write('label local\n')
    masterconf.write('  menu label Boot from local drive\n')
    masterconf.write('  localboot 0xffff\n')

    # We're done writing to the master isolinux.cfg file!
    masterconf.close()
    if efi:
        masterueficonf.close()
        boot_images = [ os.path.join(imagedir, 'images/efiboot.img'),
                        os.path.join(imagedir, 'images/macboot.img') ]
        for boot_image in boot_images:
            if os.path.isfile(boot_image):
                if verbose:
                    print 'Preparing to modify bootloader {0}'.format(boot_image)
                #os.chmod(boot_image, stat.S_IWRITE)
                if verbose:
                    print 'Mounting {0} to {1}'.format(boot_image, mountdir)
                mount_command = 'mount -o loop "{0}" "{1}"'.format(boot_image, mountdir)
                result = os.system(mount_command)
                if result:
                    sys.exit('I tried to run {0}, but it failed. Exiting.'.format(mount_command))
                if verbose:
                    print 'Copying {0} to the image {1}'.format(ueficonf, boot_image)
                shutil.copy2(ueficonf, os.path.join(mountdir, 'EFI/BOOT'))
                if verbose:
                    print 'Sleeping for 3 seconds before unmounting {0}'.format(mountdir)
                time.sleep(3)
                unmount_command = 'umount "{0}"'.format(mountdir)
                result = os.system(unmount_command)
                if result:
                    sys.exit('I tried to run {0}, but it failed. Exiting.'.format(unmount_command))

    if verbose:
        print 'Copying /usr/share/syslinux/isolinux.bin to {0}'.format(isolinuxdir)
    shutil.copy2('/usr/share/syslinux/isolinux.bin', isolinuxdir)
    if verbose:
        print 'Copying /usr/share/syslinux/vesamenu.c32 to {0}'.format(isolinuxdir)
    shutil.copy2('/usr/share/syslinux/vesamenu.c32', isolinuxdir)
    if verbose:
        print 'Copying /usr/share/syslinux/ldlinux.c32 to {0}'.format(isolinuxdir)
    shutil.copy2('/usr/share/syslinux/ldlinux.c32', isolinuxdir)
    if verbose:
        print 'Copying /usr/share/syslinux/libcom32.c32 to {0}'.format(isolinuxdir)
    shutil.copy2('/usr/share/syslinux/libcom32.c32', isolinuxdir)
    if verbose:
        print 'Copying /usr/share/syslinux/libutil.c32 to {0}'.format(isolinuxdir)
    shutil.copy2('/usr/share/syslinux/libutil.c32', isolinuxdir)
    # We only need to copy the ifcpu64.c32 file if we have multiarchentries in the isolinux.cfg
    if multiarchentries:
        if verbose:
            print 'Copying /usr/share/syslinux/ifcpu64.c32 to {0}'.format(isolinuxdir)
        shutil.copy2('/usr/share/syslinux/ifcpu64.c32', isolinuxdir)
    if efi:
        #mkisofs_command = '/usr/bin/mkisofs -allow-leading-dots -allow-multidot -l -relaxed-filenames -no-iso-translate -J -R -v -V {0} -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -eltorito-alt-boot -e images/efiboot.img -no-emul-boot -eltorito-alt-boot -e images/macboot.img -no-emul-boot -allow-limited-size -o {1} {2}'.format(targetname, targetiso, imagedir)
        mkisofs_command = '/usr/bin/mkisofs {0} -U -J -joliet-long -R -v -V {1} -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -eltorito-alt-boot -e images/efiboot.img -no-emul-boot -eltorito-alt-boot -e images/macboot.img -no-emul-boot -allow-limited-size -o {2} {3}'.format(volumeheaderinfo, targetname, targetiso, imagedir)
    else:
        #mkisofs_command = '/usr/bin/mkisofs -allow-leading-dots -allow-multidot -l -relaxed-filenames -no-iso-translate -J -R -v -V {0} -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -allow-limited-size -o {1} {2}'.format(targetname, targetiso, imagedir)
        mkisofs_command = '/usr/bin/mkisofs {0} -U -J -joliet-long -R -v -V {1} -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -allow-limited-size -o {2} {3}'.format(volumeheaderinfo, targetname, targetiso, imagedir)
    if verbose:
        print 'Running mkisofs to make {0}:'.format(targetiso)
        print mkisofs_command
    os.system(mkisofs_command)
    # subprocess.Popen(mkisofs_command)
    if verbose:
        print 'Running isohybrid on the ISO'
    if efi:
        isohybrid_command = '/usr/bin/isohybrid --uefi --mac {0}'.format(targetiso)
    else:
        isohybrid_command = '/usr/bin/isohybrid {0}'.format(targetiso)
    os.system(isohybrid_command)

def makegrubimage(isolist, imagedir, mountdir, timeout, bootdefaultnum, grubarch, targetiso, targetname, isodir, verbose):
    # Make the grub directory
    grubdir = os.path.join(imagedir, 'boot/grub')
    grubconf = os.path.join(grubdir, 'grub.conf')
    if verbose:
        print 'Making the directory for grub in IMAGEDIR: {0}'.format(grubdir)
    try:
        os.makedirs(grubdir)
    except:
        error = sys.exc_info()[1]
        sys.exit('I was trying to make the grub directory as {0}, but I failed with error {1}. Exiting.'.format(grubdir, error))
    # Write our header
    f = open(grubconf, 'w')
    f.write('timeout={0}\n'.format(timeout))
    f.write('default={0}\n'.format(bootdefaultnum))

    for iso in isolist:
        basename = os.path.basename(iso)
        iso_basename = os.path.splitext(basename)[0]

        # Now, we need to loopback mount this ISO.
        if verbose:
	    print 'Loopback mounting {0} on {1}'.format(iso, mountdir)
        mount_command = 'mount -o loop "{0}" "{1}"'.format(iso, mountdir)
        result = os.system(mount_command)
        if result:
	    sys.exit('I tried to run {0}, but it failed. Exiting.'.format(mount_command))
        # We used to check for "live" in the isolinux/isolinux.cfg, but all Fedora ISOs now
        # pass that check, including the install media! Now, we just look for .discinfo. If it
        # is present, we know we're not on a live ISO.
        discinfo_file = os.path.join(mountdir, '.discinfo')
        if os.path.isfile(discinfo_file):
            if verbose:
                print '{0} found. Must be an InstallISO.'.format(discinfo_file)
            iso_type_live = False
        else:
            if verbose:
                print '{0} _NOT_ found. Must be a LiveISO.'.format(discinfo_file)
            iso_type_live = True

        if iso_type_live:
	    # Okay, this is a Live ISO.
	    if verbose:
		print '{0} is a Live ISO. Copying files to {1}.'.format(iso, os.path.join(imagedir, iso_basename))
	    shutil.copytree(mountdir, os.path.join(imagedir, iso_basename))
	    if verbose:
		print 'Writing ISO specific entry for {0} into grub configs.'.format(iso_basename)
	    f.write('title {0}\n'.format(iso_basename))
	    f.write('    kernel /{0}/isolinux/vmlinuz root=live:LABEL={1} rd.live.dir=/{0}/LiveOS/ rootfstype=auto ro liveimg quiet  rhgb\n'.format(iso_basename, targetname))
            f.write('	 initrd /{0}/isolinux/initrd.img\n'.format(iso_basename))
            submenu = open(os.path.join(grubdir, 'submenu.lst'), 'w')
	    submenu.write('title {0}\n'.format(iso_basename))
	    submenu.write('    kernel /{0}/isolinux/vmlinuz root=live:LABEL={1} rd.live.dir=/{0}/LiveOS/ rootfstype=auto ro liveimg quiet  rhgb check\n'.format(iso_basename, targetname))
	    submenu.write('    initrd /{0}/isolinux/initrd.img\n'.format(iso_basename))
	    submenu.close()
	    makehelperdirs(imagedir, iso_basename, "grub", verbose)
	else:
	    # Not a Live ISO.
	    if verbose:
		print '{0} is NOT a Live ISO. Copying files to {1}.'.format(iso, os.path.join(imagedir, iso_basename))
            makehelperdirs(imagedir, iso_basename, "grub", verbose)
	    shutil.copy2(os.path.join(mountdir, 'isolinux/vmlinuz'), os.path.join(imagedir, iso_basename, 'boot/'))
	    shutil.copy2(os.path.join(mountdir, 'isolinux/initrd.img'), os.path.join(imagedir, iso_basename, 'boot/'))
            if os.path.isfile(os.path.join(mountdir, 'images/install.img')):
	        shutil.copy2(os.path.join(mountdir, 'images/install.img'), os.path.join(imagedir, iso_basename, 'images/'))
	    f.write('title {0}\n'.format(iso_basename))
	    f.write('    kernel /{0}/boot/vmlinuz repo=hd:LABEL={1}:/{0}/\n'.format(iso_basename, targetname))
	    f.write('    initrd /{0}/boot/initrd.img\n'.format(iso_basename))
	    if verbose:
		print 'Copying {0} into {1}.'.format(iso, os.path.join(imagedir, iso_basename))
	    shutil.copy2(iso, os.path.join(imagedir, iso_basename))
        # Unmount the iso
        unmount_command = 'umount "{0}"'.format(mountdir)
        result = os.system(unmount_command)
        if result:
            sys.exit('I tried to run {0}, but it failed. Exiting.'.format(unmount_command))

    # We're done writing to the grub file!
    f.close()

    os.symlink('grub.conf', os.path.join(grubdir, 'menu.lst'))
    shutil.copy2('/usr/share/grub/{0}-redhat/stage2_eltorito'.format(grubarch), grubdir)
    mkisofs_command = '/usr/bin/mkisofs -J -R -v -V {0} -b boot/grub/stage2_eltorito -no-emul-boot -boot-load-size 4 -boot-info-table -allow-limited-size -o {1} {2}'.format(targetname, targetiso, imagedir)
    if verbose:
	print 'Running mkisofs to make {0}:'.format(targetiso)
        print mkisofs_command
    os.system(mkisofs_command)
    # subprocess.Popen(mkisofs_command)

def parse_isolist(isolist, isodir, parsedisolist, verbose):
    for iso in isolist:
	# First, lets check if we've been passed a wildcard
	# and if so, glob it out to the specific items.
	if '*' in iso:
	    if verbose:
		print '{0} is a wildcard, looking for matches ...'.format(iso)
	    globlist = glob.glob(iso)
	    # Did we find anything?
	    if globlist:
                if verbose:
                    print 'Found matches! Adding them now.'
	        for globbediso in globlist:
		    parsedisolist.append(globbediso)
            else:
                # Uhoh. This wildcard didn't match anything. Lets append isodir and try again.
                isodir_plus_iso = os.path.join(isodir,iso)
                if verbose:
                    print 'No matches found. Trying again with ISODIR ...'
		isodir_plus_iso = os.path.join(isodir,iso)
		globlist = glob.glob(isodir_plus_iso)
                if globlist:
                    if verbose:
                        print 'Found matches! Adding them now.'
                    for globbediso in globlist:
                        parsedisolist.append(globbediso)
                else:
                    if verbose:
                        print 'No matches found.'
                    # I can't find any matches for this wildcard. Bail out!
                    sys.exit('Error: You specified {0}, but I could not find any matches. Exiting.'.format(iso))
	else:
	    # Okay, this is a normal non-wildcard item.
	    # Check if it exists as is (fullpath)
            if verbose:
                print 'Checking for {0} ...'.format(iso)
	    if os.path.isfile(iso):
                if verbose:
                    print 'Found!'
	        parsedisolist.append(iso)
            else:
                # Okay, no. Now we'll look in ISODIR
                isodir_plus_iso = os.path.join(isodir,iso)
                if verbose:
                    print 'Not found!'
                    print 'Checking for {0} ...'.format(isodir_plus_iso)
                if os.path.isfile(isodir_plus_iso):
                    if verbose:
                        print 'Found!'
                    parsedisolist.append(isodir_plus_iso)
                else:
		    if verbose:
			print 'Not found!'
                    # Uhoh. This item doesn't exist. Evacuate!
		    sys.exit('Error: You specified {0}, but I could not find it. Exiting.'.format(iso))


# This is where the magic happens
if __name__ == '__main__':

    # Locale magic
    locale.setlocale(locale.LC_ALL, '')

    # Create the parser object
    parser = argparse.ArgumentParser(description = my_description)

    parser.add_argument('--bootdefault', nargs = '?', metavar='NAMEOF.ISO',
                        help = 'Selects the default boot target by filename, if not set, defaults to the first item in the ISO list.')

    parser.add_argument('--clean', action = 'store_true',
                        help = 'Clean out and remove any files found in IMAGEDIR before starting.')

    parser.add_argument('--efi', action = 'store_true',
                        help = 'Enable EFI support.')

    parser.add_argument('--grub', action = 'store_true',
                        help = 'Use grub to handle the boot menu. The default is to use isolinux.')

    parser.add_argument('--grubarch', nargs = '?', default = 'i386', metavar = 'i386|x86_64',
                        help = 'Architecture for grub files. Valid choices are i386 or x86_64. Default is i386.')

    parser.add_argument('-i', '--isos', nargs = '*',
                        help = 'List of ISOs to use, either with full path or in ISODIR.')

    parser.add_argument('--imagedir', nargs = '?', default = os.path.join(os.curdir, 'image'),
                        help = 'Working directory for image creation. Defaults to {0}'.format(os.path.join(os.curdir, 'image')))

    parser.add_argument('--isodir', nargs = '?', default = os.curdir,
                        help = 'System Directory where source ISOs (and CHECKSUM files) are stored. Defaults to .')

    parser.add_argument('--isolinuxsplash', nargs = 1, default = '/usr/share/anaconda/boot/syslinux-splash.png',
                        help = 'Full path to isolinux splash image. Defaults to /usr/share/anaconda/boot/syslinux-splash.png')

    parser.add_argument('--mountdir', nargs = '?', default = os.path.join(os.curdir, 'mnt'),
                        help = 'Working directory for temporarily mounting source ISOs. Defaults to {0}'.format(os.path.join(os.curdir, 'mnt')))

    parser.add_argument('--nomultiarch', action = 'store_true',
                        help = 'Disable multiarch support in isolinux.cfg (detect whether system is ia32 or x86_64 and choose correct image). \
                                The default is to enable multiarch support. \
                               	Please note: You must pass matching i*86 and x86_64 isos in -i in order for this to work.')

    parser.add_argument('--nosort', action = 'store_true',
			help = 'Do not sort the list of ISOs in locale specific alphabetic order. \
                                The default is to perform this sort.')

    parser.add_argument('--target', nargs = '?', default = 'Multi-Boot.iso', metavar = 'Foo.iso',
                        help = 'Filename of target Multi Boot ISO image. Defaults to Multi-Boot.iso')

    parser.add_argument('--targetname', nargs = '?', metavar = 'NAME', default = 'Multi-Boot',
                        help = 'Name of Multi Boot ISO, not to be confused with filename. Defaults to Multi-Boot.')

    parser.add_argument('--timeout', metavar = 'INT', type = int, nargs = 1, default = 10,
                        help = 'Timeout for boot selection, in seconds, default is 10.')

    parser.add_argument('--preparer', nargs = 1, default=None,
                        help = 'Text string (128 characters max) that will be written into the volume header that describes the preparer of the ISO.')

    parser.add_argument('--publisher', nargs = 1, default=None,
                        help = 'Text string (128 characters max) that will be written into the volume header that describes the publisher of the ISO.')

    parser.add_argument('--application', nargs = 1, default=None,
                        help = 'Text string (128 characters max) that will be written into the volume header that describes the application that will be on the ISO.')

    # Verbosity, for debugging
    parser.add_argument('-v', '--verbose', action = 'store_true',
                        help = 'Run with verbose debug output')

    parser.add_argument('--version', action = 'version', version = my_description,
                        help = 'Print program version information and exit')

    # Parse the args
    args = parser.parse_args()

    if os.geteuid() != 0:
	sys.exit('You must have root privileges to run this script successfully. Exiting.')

    # Are we being verbose? Lets get a summary of what we've learned from our args.
    if args.verbose:
        print 'Verbose mode is on.'
        print 'IMAGEDIR is set to {0}'.format(args.imagedir)
        print 'ISODIR is set to {0}'.format(args.isodir)
        print 'MOUNTDIR is set to {0}'.format(args.mountdir)

    # Check the target name. Does it already exist?
    if os.path.isfile(args.target):
        sys.exit('The specified target ISO {0} already exists. Delete it before running this script. Exiting.'.format(args.target))

    # Check the working directory (IMAGEDIR). Does it already exist?
    if os.path.isdir(args.imagedir):
        if args.verbose:
            print 'Note: IMAGEDIR already exists.'
        if os.listdir(args.imagedir):
            # Uh oh. There are files in IMAGEDIR. Did the user tell us to clean it out?
            if args.clean:
                if args.verbose:
                    print 'Deleting IMAGEDIR and recreating it to ensure a clean and empty directory.'
                shutil.rmtree(args.imagedir)
                os.makedirs(args.imagedir)
            else:
                sys.exit('IMAGEDIR ({0}) exists and has files in it. Use --clean to empty it. Exiting.'.format(args.imagedir))
    else:
        # IMAGEDIR doesn't exist, so we'll make it now.
        if args.verbose:
            print 'IMAGEDIR does not exist, creating it now.'
        try:
            os.makedirs(args.imagedir)
        except:
            error = sys.exc_info()[1]
            sys.exit('I was trying to make IMAGEDIR as {0}, but I failed with error {1}. Exiting.'.format(args.imagedir, error))

    # Check the mount directory (MOUNTDIR). Does it already exist?
    if os.path.isdir(args.mountdir):
        if args.verbose:
            print 'Note: MOUNTDIR already exists.'
        # Check to see if the system thinks something is mounted there already.
        if os.path.ismount(args.mountdir):
            sys.exit('Something is mounted at MOUNTDIR ({0}). Please unmount it and restart.'.format(args.mountdir))
    else:
        # MOUNTDIR doesn't exist, so we'll make it now.
        if args.verbose:
            print 'MOUNTDIR does not exist, creating it now.'
        try:
            os.makedirs(args.mountdir)
        except:
            error = sys.exc_info()[1]
            sys.exit('I was trying to make MOUNTDIR as {0}, but I failed with error {1}. Exiting.'.format(args.mountdir, error))

    if args.isos:
	isolist = []
	parse_isolist(args.isos, args.isodir, isolist, args.verbose)
    else:
        sys.exit('No ISOs specified, nothing to do, exiting.')

    if args.nosort:
	if args.nomultiarch:
	    sys.exit('We need sorting to make multiarch support sane. Bailing out. If you really want to disable sorting, also pass --nomultiarch.')
	else:
	    if args.verbose:
                print 'Not sorting list of found ISOs, user override.'
    else:
        if args.verbose:
            print 'Sorting list of found ISOs.'
        sortedlist = sorted(isolist, cmp=locale.strcoll)
        isolist = sortedlist

    # The default boot choice is the first item in the list, unless the user specifies otherwise.
    bootdefaultnum = 0

    if args.bootdefault:
        # Let's make sure it is in the isolist first.
        if args.bootdefault in isolist:
            bootdefaultnum = isolist.index(args.bootdefault)
        else:
           # Maybe we need to add the ISODIR to it?
           if os.path.join(args.isodir,args.bootdefault) in isolist:
               bootdefaultnum = isolist.index(os.path.join(args.isodir,args.bootdefault))
           else:
               # Bail out since I can't find the boot
               sys.exit('Could not find the specified bootdefault ISO ({}) in the list of ISOs. Exiting.'.format(args.bootdefault))
        bootdefaultiso = args.bootdefault
    else:
        bootdefaultiso = isolist[0]


    if args.verbose:
	print 'Here are the ISOs that I am going to add:'
	for item in isolist:
	    print item
        print 'The default is {0} in position {1}'.format(isolist[bootdefaultnum], bootdefaultnum)

    volumeheaderinfo = ""

    if args.preparer != None:
        volumeheaderinfo += ' -p "{0}"'.format(args.preparer[0])
        if args.verbose:
            print 'PREPARER is set to {0}'.format(args.preparer[0])

    if args.publisher != None:
        volumeheaderinfo += ' -publisher "{0}"'.format(args.publisher[0])
        if args.verbose:
            print 'PUBLISHER is set to {0}'.format(args.publisher[0])

    if args.application != None:
        volumeheaderinfo += ' -A "{0}"'.format(args.application[0])
        if args.verbose:
            print 'APPLICATION is set to {0}'.format(args.application[0])

    volumeheaderinfo = volumeheaderinfo.strip()
    if args.verbose:
        print 'volumeheaderinfo = {0}'.format(volumeheaderinfo)

    if args.efi:
       # Sanity check for shim
       if os.path.isfile('/boot/efi/EFI/fedora/shim.efi'):
           if args.verbose:
                print 'Found /boot/efi/EFI/fedora/shim.efi. Assuming shim is installed properly'
       else:
           sys.exit('Could not find /boot/efi/EFI/fedora/shim.efi ? Perhaps the shim package is not installed?')
       # Sanity check for shim-unsigned
       if os.path.isfile('/boot/efi/EFI/fedora/MokManager.efi'):
           if args.verbose:
       	       	print 'Found /boot/efi/EFI/fedora/MokManager.efi. Assuming shim-unsigned is installed properly'
       else:
       	   sys.exit('Could not find /boot/efi/EFI/fedora/MokManager.efi ? Perhaps the shim-unsigned package is not installed?')
       # Sanity check for grub2 EFI files
       if os.path.isfile('/boot/efi/EFI/fedora/gcdx64.efi'):
           if args.verbose:
    	       	print 'Found /boot/efi/EFI/fedora/gcdx64.efi. Assuming grub2-efi is installed properly'
       else:
       	   sys.exit('Could not find /boot/efi/EFI/fedora/gcdx64.efi ? Perhaps the grub2-efi package is not installed?')

    if args.grub:
        # Generating multiboot grub config
        if args.grubarch != 'i386' and args.grubarch != 'x86_64':
	    sys.exit('The grubarch you have specified ({0}) is invalid. Exiting.'.format(args.grubarch))

        if args.verbose:
            print 'Generating multiboot grub image'
        makegrubimage(isolist, args.imagedir, args.mountdir, args.timeout, bootdefaultnum, args.grubarch, args.target, args.targetname, args.isodir, args.verbose)
    else:
	if args.verbose:
	    print 'Generating multiboot isolinux image'
        # Sanity check
        if os.path.isfile('/usr/share/syslinux/isolinux.bin'):
            if args.verbose:
                 print 'Found /usr/share/syslinux/isolinux.bin. Assuming syslinux is installed properly'
        else:
            sys.exit('Could not find /usr/share/syslinux/isolinux.bin ? Perhaps syslinux is not installed?')
	makeisolinuximage(isolist, args.imagedir, args.mountdir, args.timeout, bootdefaultiso, args.target, args.targetname, args.isolinuxsplash, args.isodir, args.nomultiarch, args.efi, bootdefaultnum, args.verbose, volumeheaderinfo)
