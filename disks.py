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


def create_label(d, size, swap):
    if is_b2():
        l_type = "dos"
        p_type = "MBR"
    else:
        l_type = "gpt"
        p_type = "GPT"
    logging.info("Creating %s label, system %.1f GiB size partition and swap %.1f MiB size on %s" %
                 (p_type, size, swap, d))
    fdisk_input = "label: %s\n,%.1fGiB,L\n,,S\n" % (l_type, size)
    r = runcmd2(["sfdisk", "/dev/%s" % (d,)], fdisk_input)
    return r == 0


def wipe_label(d):
    logging.info("Wiping existing partition label on %s" % (d, ))
    r = runcmd1(["sgdisk", "-Z", "/dev/%s" % (d,)])
    return r == 0


def prepare_disk(wipe, size, swap, dest):
    d = disks_details[dest]
    if size == 'full':
        min_size = 10*1024*1024*1024 + swap*1024*1024
    else:
        min_size = size*1024*1024*1024 + swap*1024*1024

    # We take a 1 meg unused zone on disk start
    if d['size'] - 1024*1024 < min_size:
        logging.error("Destination disk is too small (min_size: %s; %s size: %s)!" %
                      (sizeof_fmt(min_size), dest, sizeof_fmt(d['size'])))
        return False

    if size == 'full':
        size = (d['size'] - (swap - 1)*1024*1024) / float(1024*1024*1024)

    if d['type'] is None:
        return create_label(dest, size, swap)
    elif wipe:
        if wipe_label(dest):
            return create_label(dest, size, swap)
        logging.error("Unable to wipe partition label on %s" % (dest, ))
        return False
    elif len(d['parts']) == 0:
        logging.info("Empty disk label found ; replacing it with adapted label")
        if wipe_label(dest):
            return create_label(dest, size, swap)
        logging.error("Unable to wipe existing partition label on %s" % (dest, ))
        return False
    elif d['type'] == 'gpt':
        if is_b2():
            logging.error("Cannot use existing GPT label on the Bubba|2")
            return False
        else:
            # TODO
            if 1 in d['parts']:
                pass
            else:
                logging.error("Missing reusable first partition on the disk")
                return False
            print d
            return True
    elif d['type'] == 'mbr':
        if not is_b2():
            logging.warning("Using MBR label on the B3 is not recommended (GPT is preferred); continuing anyway")
        # TODO
        print d
        return True
