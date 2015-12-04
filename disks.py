import os
import logging
from utils import InvalidConf, DiskError, is_b2, sizeof_fmt, runcmd1, runcmd2
import re
import partitions

__author__ = 'Charles Leclerc <leclerc.charles@gmail.com>'

disks_details = dict()


def list_sata_disks():
    res = []
    for d in [f for f in os.listdir('/sys/block') if re.match('sd[a-z]$', f)]:
        if '/ata' in os.readlink(os.path.join('/sys/block', d)):
            res.append(d)
    return sorted(res)


def inventory_existing():
    global disks_details
    try:
        disks_details = {}
        for dev in list_sata_disks():
            logging.info('Checking /dev/%s' % (dev,))
            disks_details[dev] = partitions.get_disk_details(dev)
    except DiskError:
        return False
    except InvalidConf:
        return False
    return True


def create_label(d, size, swap, full):
    if is_b2():
        l_type = "dos"
        p_type = "MBR"
    else:
        l_type = "gpt"
        p_type = "GPT"
    logging.info("Creating %s label, system %.1f GiB size partition and swap %.1f MiB size on %s" %
                 (p_type, size, swap, d))
    if full:
        fdisk_input = "label: %s\n,%.1fGiB,L\n,,S\n" % (l_type, size)
    else:
        fdisk_input = "label: %s\n,%.1fGiB,L\n,%.1fMiB,S\n" % (l_type, size, swap)
    if runcmd2(["sfdisk", "/dev/%s" % (d,)], fdisk_input) != 0:
        return False
    else:
        return 2


def wipe_label(d):
    logging.info("Wiping existing partition label on %s" % (d, ))
    r = runcmd1(["sgdisk", "-Z", "/dev/%s" % (d,)])
    return r == 0


def check_and_prepare_disk(wipe, size, swap, dest):
    d = disks_details[dest]
    if size == 'full':
        full = True
        min_size = 8*1024*1024*1024 + swap*1024*1024
    else:
        full = False
        min_size = size*1024*1024*1024 + swap*1024*1024

    # We take a 1 meg unused zone on disk start
    if d['size'] - 1024*1024 < min_size:
        logging.error("Destination disk is too small (min_size: %s; %s size: %s)!" %
                      (sizeof_fmt(min_size), dest, sizeof_fmt(d['size'])))
        return False

    if size == 'full':
        size = (d['size'] - (swap - 1)*1024*1024) / float(1024*1024*1024)

    if d['type'] is None:
        return create_label(dest, size, swap, full)
    elif wipe:
        if wipe_label(dest):
            return create_label(dest, size, swap, full)
        logging.error("Unable to wipe partition label on %s" % (dest, ))
        return False
    elif len(d['parts']) == 0:
        logging.warning("Empty disk label found ; replacing it with adapted label")
        if wipe_label(dest):
            return create_label(dest, size, swap, full)
        logging.error("Unable to wipe existing partition label on %s" % (dest, ))
        return False
    elif d['type'] == 'gpt':
        if is_b2():
            logging.error("Cannot use existing GPT label on the Bubba|2")
            return False
    elif d['type'] == 'mbr':
        if not is_b2():
            logging.warning("Using MBR label on the B3 is not recommended (GPT is preferred); continuing anyway")

    if 1 in d['parts']:
        if d['type'] == 'mbr' and d['parts'][1]['id'] in partitions.ext_codes:
            logging.error("Will not overwrite an extended first partition !")
            return False
        if d['parts'][1]['size'] < 8*1024*1024*1024:
            logging.error("The existing (%s) system partition does not meet minimal size criteria of 8 GiB" %
                          (sizeof_fmt(d['parts'][1]['size'], )))
            return False
        if not partitions.check_type(1, d, "data"):
            return False
        logging.info("Using existing system partition (%s1, size: %s) " % (dest, sizeof_fmt(d['parts'][1]['size'])), )
    else:
        logging.error("Missing reusable first partition on %s" % (dest, ))
        return False

    for n, p in d['parts'].iteritems():
        if n == 1:
            continue
        if d['type'] == 'mbr' and p['id'] == '82' or \
           d['type'] == 'gpt' and p['code'] == '8200':
            if p['size'] < 256*1024*1024:
                logging.error("The existing swap partition (%d) on %s does not meet minimal size criteria" % (n, dest))
                return False
            logging.info("Using existing swap partition (%s%d, size: %s) " %
                         (dest, n, sizeof_fmt(p['size'])))
            return n

    logging.error("Missing usable swap partition on %s" % (dest, ))
    return False

