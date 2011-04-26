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

name = 'Multiboot Media Creator'
version = 0.5
my_description = '{0} {1}'.format(name, version)

def makehelperdirs(imagedir, iso_basename, type, verbose):
    if type == "grub":
        dirs = ['boot', 'images', 'CHECKSUM']
    else:
        dirs = ['isolinux', 'images', 'CHECKSUM']
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

def makeisolinuximage(isolist, imagedir, mountdir, timeout, bootdefaultnum, targetiso, targetname, isolinuxsplash, isodir, nomultiarch, verbose):
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

    # Open our master config file.
    masterconf = open(isolinuxconf, 'w')

    # Write our header into the master config file
    # TODO: This is based on the Fedora 14 header, probably needs to be cleaned up.

    masterconf.write('default vesamenu.c32\n')
    masterconf.write('timeout {0}\n'.format(timeout))
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

    # This file is where we store the normal target entries
    ffile = os.path.join(imagedir, 'normaltargets.part')
    f = open(ffile, 'w')

    # This file is where we store the isolinux config bits for Live Images
    bvtfile = os.path.join(imagedir, 'basicvideotargets.part')
    bvt = open(bvtfile, 'w')
    bvt.write('menu begin\n')
    bvt.write('menu title Boot (Basic Video)\n')
    bvt.write('\n')

    # This file is where we store the Verify Media targets
    # If all our targets are non-live, we won't have anything here.
    # Hence, we default to false.
    verifyentries = False
    vtfile = os.path.join(imagedir, 'verifytargets.part')
    vt = open(vtfile, 'w') 
    vt.write('menu begin\n')
    vt.write('menu title Verify and Boot...\n')
    vt.write('\n')

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

        # isolinux can't read directories or files longer than 31 characters.
        # Truncate if we need to. (Yes, this could cause issues. :P)
        if len(iso_basename) > 31:
            small_iso_basename = iso_basename[:31]
            if verbose:
                 print '{0} is {1}, this is longer than the isolinux 31 character max.'.format(iso_basename, len(iso_basename))
                 print 'In the isolinux.cfg, we will refer to it as {0}.'.format(small_iso_basename)
        else:
            small_iso_basename = iso_basename

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
        isolinux_config = open(os.path.join(mountdir, 'isolinux/isolinux.cfg'), 'r')
        isolinux_config_text = isolinux_config.read()
        isolinux_config.close()
        search_string = 'live'
        index = isolinux_config_text.find(search_string)
        # If index is -1, then the search_string is not in the text.
        if index >= 0:
            # Okay, this is a Live ISO.
            if verbose:
                print '{0} is a Live ISO. Copying files to {1}.'.format(iso, os.path.join(imagedir, iso_basename))
            shutil.copytree(mountdir, os.path.join(imagedir, iso_basename))

            if pairfound:
                x86_64_basename = os.path.basename(x86_64_iso)
                x86_64_iso_basename = os.path.splitext(x86_64_basename)[0]

                pairname = re.sub(r'i[3456]+86-', '', iso_basename)
                pretty_pairname = re.sub(r'-', ' ', pairname)
		mat.write('label {0}\n'.format(pairname))
                mat.write('  menu label Autoselect x86_64 / i686 {0}\n'.format(pretty_pairname))
                mat.write('  kernel ifcpu64.c32\n')
                # This only works if the ia32 target is set as the default, since it it will trigger the target creation.
                if counter == bootdefaultnum:
                    mat.write('  menu default\n')
                    # We need to know that we set the paired target as the default
                    pairedtarget_is_default = True
                mat.write('  append {0} -- {1}\n'.format(x86_64_iso_basename, iso_basename))
                mat.write('\n')

	    # Write out non-multiboot items
            if verbose:
                print 'Writing ISO specific entry for {0} into isolinux configs.'.format(iso_basename)
            f.write('label {0}\n'.format(iso_basename))
            f.write('  menu label Boot {0}\n'.format(pretty_iso_basename))
            if counter == bootdefaultnum:
                if pairedtarget_is_default:
                   # The paired target inherited the default setting, so we don't set it here.
                   if verbose:
                      print 'Since the default is in the paired target, we are not setting this individual item as the default.'
                else:
                   f.write('  menu default\n')
            # Note that we only need the small_iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
            f.write('  kernel /{0}/isolinux/vmlinuz0\n'.format(small_iso_basename))
            f.write('  append initrd=/{0}/isolinux/initrd0.img root=live:CDLABEL={1} live_dir=/{2}/LiveOS/ rootfstype=auto ro liveimg quiet rhgb rd_NO_LUKS rd_NO_MD rd_NO_DM\n'.format(small_iso_basename, targetname, iso_basename))
            f.write('\n')

            # Now, we write out the basic video entry
            bvt.write('label {0}_basicvideo\n'.format(iso_basename))
            bvt.write('  menu label {0} (Basic Video)\n'.format(pretty_iso_basename))
            if counter == bootdefaultnum:
                bvt.write('  menu default\n')
            # Note that we only need the small_iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
            bvt.write('  kernel /{0}/isolinux/vmlinuz0\n'.format(small_iso_basename))
            bvt.write('  append initrd=/{0}/isolinux/initrd0.img root=live:CDLABEL={1} live_dir=/{2}/LiveOS/ rootfstype=auto ro liveimg quiet rhgb rd_NO_LUKS rd_NO_MD rd_NO_DM xdriver=vesa nomodeset\n'.format(small_iso_basename, targetname, iso_basename))            
            bvt.write('\n')

            # And last, we write out the verify entry
            verifyentries = True
            vt.write('label {0}_verify\n'.format(iso_basename))
            vt.write('  menu label Verify and Boot {0}\n'.format(pretty_iso_basename))
            if counter == bootdefaultnum:
                vt.write('  menu default\n')
            # Note that we only need the small_iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
            vt.write('  kernel /{0}/isolinux/vmlinuz0\n'.format(small_iso_basename))
            vt.write('  append initrd=/{0}/isolinux/initrd0.img root=live:CDLABEL={1} live_dir=/{2}/LiveOS/ rootfstype=auto ro liveimg quiet rhgb rd_NO_LUKS rd_NO_MD rd_NO_DM check\n'.format(small_iso_basename, targetname, iso_basename))
            vt.write('\n')

            makehelperdirs(imagedir, iso_basename, "isolinux", verbose)
            checksum_name = '{0}-CHECKSUM'.format(iso_basename)
            checksum_file = os.path.join(isodir, checksum_name)
            if os.path.isfile(checksum_file):
                if verbose:
                    print 'Copying {0} checksum file to {1}.'.format(checksum_file, os.path.join(imagedir, iso_basename, 'CHECKSUM/'))
                shutil.copy2(checksum_file, os.path.join(imagedir, iso_basename, 'CHECKSUM/'))
            else:
                print 'Could not locate {0} in isodir ({1}). Continuing, but {2} will always fail verification.\n'.format(checksum_name, isodir, iso_basename)

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
                mat.write('  menu label Autoselect x86_64 / i686 {0}\n'.format(pretty_pairname))
                mat.write('  kernel ifcpu64.c32\n')
                # This only works if the ia32 target is set as the default, since it it will trigger the target creation.
                if counter == bootdefaultnum:
                    mat.write('  menu default\n')
                mat.write('  append {0} -- {1}\n'.format(x86_64_iso_basename, iso_basename))
                mat.write('\n')

            f.write('label {0}\n'.format(iso_basename))
            f.write('  menu label Install {0}\n'.format(pretty_iso_basename))
            if counter == bootdefaultnum:
                if pairedtarget_is_default:
                   # The paired target inherited the default setting, so we don't set it here.
                   if verbose:
                      print 'Since the default is in the paired target, we are not setting this individual item as the default.'
                else:
                   f.write('  menu default\n')
            f.write('  kernel /{0}/isolinux/vmlinuz\n'.format(small_iso_basename))
            # Note that	we only	need the small_iso_basename for	pathing	that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
            f.write('  append initrd=/{0}/isolinux/initrd.img repo=hd:LABEL={1}:/{2}/\n'.format(small_iso_basename, targetname, iso_basename))
            f.write('\n')

            # Now, we write out the basic video entry
            bvt.write('label {0}_basicvideo\n'.format(iso_basename))
            bvt.write('  menu label {0} (Basic Video)\n'.format(pretty_iso_basename))
            if counter == bootdefaultnum:
                bvt.write('  menu default\n')
            # Note that we only need the small_iso_basename for pathing that isolinux will use (kernel and initrd path). All other pathing should use iso_basename.
            bvt.write('  kernel /{0}/isolinux/vmlinuz\n'.format(small_iso_basename))
            bvt.write('  append initrd=/{0}/isolinux/initrd.img repo=hd:LABEL={1}:/{2} xdriver=vesa nomodeset\n'.format(small_iso_basename, targetname, iso_basename))
            bvt.write('\n')

            # Only Live ISOs have a verify mode as a command line option. Non-Live ISOs always prompt to check in anaconda.
            # So we don't need to write anything to vt here.

            if verbose:
                print 'Copying {0} into {1}.'.format(iso, os.path.join(imagedir, iso_basename))
            shutil.copy2(iso, os.path.join(imagedir, iso_basename))
            # Figure out what the CHECKSUM name should be
            p = re.compile( '(DVD)')
            checksum_name = p.sub( 'CHECKSUM', iso_basename)
            for checksum in glob.glob('{0}*'.format(checksum_name)):
                if verbose:
                    print 'Copying {0} checksum file to {1}.'.format(checksum, os.path.join(imagedir, iso_basename, 'CHECKSUM/'))
                shutil.copy2(checksum, os.path.join(imagedir, iso_basename, 'CHECKSUM/'))
        # Unmount the iso
        unmount_command = 'umount "{0}"'.format(mountdir)
        result = os.system(unmount_command)
        if result:
            sys.exit('I tried to run {0}, but it failed. Exiting.'.format(unmount_command))

    # We're now done writing to the multiboot and normal configs
    mat.close()
    f.close()

    # Now, we need to append mat to the master config file
    # But only if we found some multiarch entries
    if multiarchentries:
        masterconf.write(open(matfile).read())

    # Now, add the normal entries to the master config file
    masterconf.write(open(ffile).read())

    # Add the separator in the master config
    masterconf.write('menu separator\n')
    masterconf.write('\n')
    masterconf.write('menu end\n')
    masterconf.write('\n')

    # Write the footers for the menus in vt and bvt
    vt.write('menu separator\n')
    vt.write('\n')
    vt.write('label return\n')
    vt.write('  menu label Return to main menu...\n')
    vt.write('  menu exit\n')
    vt.write('\n')
    vt.write('menu end\n')

    bvt.write('menu separator\n')
    bvt.write('\n')
    bvt.write('label return\n')
    bvt.write(' 	menu label Return to main menu...\n')
    bvt.write(' 	menu exit\n')
    bvt.write('\n')
    bvt.write('menu end\n')

    # We are now done writing to vt and bvt
    vt.close()
    bvt.close()

    # We will always have bvt entries, so write them to the master file now.
    masterconf.write(open(bvtfile).read())

    # We might not have vt entries, check to see if we got any first.
    if verifyentries:
        masterconf.write(open(vtfile).read())

    # At this point, we no longer need matfile, ffile, vtfile or bvtfile, and we don't want them written on the image
    os.remove(matfile)
    os.remove(ffile)
    os.remove(vtfile)
    os.remove(bvtfile)

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
    if verbose:
        print 'Copying /usr/share/syslinux/isolinux.bin to {0}'.format(isolinuxdir)
    shutil.copy2('/usr/share/syslinux/isolinux.bin', isolinuxdir)
    if verbose:
        print 'Copying /usr/share/syslinux/vesamenu.c32 to {0}'.format(isolinuxdir)
    shutil.copy2('/usr/share/syslinux/vesamenu.c32', isolinuxdir)
    # We only need to copy the ifcpu64.c32 file if we have multiarchentries in the isolinux.cfg
    if multiarchentries:
        if verbose:
            print 'Copying /usr/share/syslinux/ifcpu64.c32 to {0}'.format(isolinuxdir)
        shutil.copy2('/usr/share/syslinux/ifcpu64.c32', isolinuxdir)
    mkisofs_command = '/usr/bin/mkisofs -allow-leading-dots -allow-multidot -l -relaxed-filenames -no-iso-translate -R -v -V {0} -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -allow-limited-size -o {1} {2}'.format(targetname, targetiso, imagedir)
    if verbose:
        print 'Running mkisofs to make {0}:'.format(targetiso)
        print mkisofs_command
    os.system(mkisofs_command)
    # subprocess.Popen(mkisofs_command)

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
        isolinux_config = open(os.path.join(mountdir, 'isolinux/isolinux.cfg'), 'r')
	isolinux_config_text = isolinux_config.read()
	isolinux_config.close()
	search_string = 'live'
	index = isolinux_config_text.find(search_string)
	# If index is -1, then the search_string is not in the text.
	if index >= 0:
	    # Okay, this is a Live ISO.
	    if verbose:
		print '{0} is a Live ISO. Copying files to {1}.'.format(iso, os.path.join(imagedir, iso_basename))
	    shutil.copytree(mountdir, os.path.join(imagedir, iso_basename))
	    if verbose:
		print 'Writing ISO specific entry for {0} into grub configs.'.format(iso_basename)
	    f.write('title {0}\n'.format(iso_basename))
	    f.write('    kernel /{0}/isolinux/vmlinuz0 root=live:LABEL={1} live_dir=/{0}/LiveOS/ rootfstype=auto ro liveimg quiet  rhgb\n'.format(iso_basename, targetname))
            f.write('	 initrd /{0}/isolinux/initrd0.img\n'.format(iso_basename))
            submenu = open(os.path.join(grubdir, 'submenu.lst'), 'w')
	    submenu.write('title {0}\n'.format(iso_basename))
	    submenu.write('    kernel /{0}/isolinux/vmlinuz0 root=live:LABEL={1} live_dir=/{0}/LiveOS/ rootfstype=auto ro liveimg quiet  rhgb check\n'.format(iso_basename, targetname))
	    submenu.write('    initrd /{0}/isolinux/initrd0.img\n'.format(iso_basename))
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
	    # Figure out what the CHECKSUM name should be
	    p = re.compile( '(DVD)')
	    checksum_name = p.sub( 'CHECKSUM', iso_basename)
	    for checksum in glob.glob('{0}*'.format(checksum_name)):
		if verbose:
		    print 'Copying {0} checksum file to {1}.'.format(checksum, os.path.join(imagedir, iso_basename, 'CHECKSUM/'))
		shutil.copy2(checksum, os.path.join(imagedir, iso_basename, 'CHECKSUM/'))
        # Unmount the iso 
        unmount_command = 'umount "{0}"'.format(mountdir)
        result = os.system(unmount_command)
        if result:
            sys.exit('I tried to run {0}, but it failed. Exiting.'.format(unmount_command))

    if os.path.isfile(os.path.join(grubdir, 'submenu.lst')):
        f.write('title Verify Live Media\n')
        f.write('    configfile /boot/grub/submenu.lst\n')

    # We're done writing to the grub file!
    f.close()

    os.symlink('grub.conf', os.path.join(grubdir, 'menu.lst'))
    shutil.copy2('/usr/share/grub/{0}-redhat/stage2_eltorito'.format(grubarch), grubdir)
    mkisofs_command = '/usr/bin/mkisofs -R -v -V {0} -b boot/grub/stage2_eltorito -no-emul-boot -boot-load-size 4 -boot-info-table -allow-limited-size -o {1} {2}'.format(targetname, targetiso, imagedir)
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

    parser.add_argument('--isolinuxsplash', nargs = 1, default = '/usr/lib/anaconda-runtime/syslinux-vesa-splash.jpg',
                        help = 'Full path to isolinux splash image. Defaults to /usr/lib/anaconda-runtime/syslinux-vesa-splash.jpg')

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

    parser.add_argument('--timeout', metavar = 'INT', type = int, nargs = 1, default = 100,
                        help = 'Timeout for boot selection, default is 100.')

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

    if args.verbose:
	print 'Here are the ISOs that I am going to add:'
	for item in isolist:
	    print item
        print 'The default is {0} in position {1}'.format(isolist[bootdefaultnum], bootdefaultnum)
        

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
	makeisolinuximage(isolist, args.imagedir, args.mountdir, args.timeout, bootdefaultnum, args.target, args.targetname, args.isolinuxsplash, args.isodir, args.nomultiarch, args.verbose)
