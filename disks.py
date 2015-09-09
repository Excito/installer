import os
import logging
from subprocess import Popen, PIPE
from threading import Thread
from utils import InvalidConf, DiskError, is_b2, is_b3, sizeof_fmt
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


def create_label(l_type, d, size, swap):
    logging.info("Creating %s label, system %s size partition and swap %s size on %s" %
                 (l_type.upper(), sizeof_fmt(size), sizeof_fmt(swap), d))

    return False


def prepare_disk(wipe, size, swap, dest):
    d = disks_details[dest]
    if size == 'full':
        min_size = 10*1024*1024*1024l + swap*1024*1024l
    else:
        min_size = size*1024*1024*1024l + swap*1024*1024l

    # We take a 1 meg unused zone on disk start
    if d['size'] - 1024*1024 < min_size:
        logging.error("Destination disk is too small (min_size: %d; %s size: %d)!" % (min_size, dest, d['size']))
        return False

    swap = swap*1024*1024

    if size == 'full':
        size = d['size'] - swap - 1024*1024
    else:
        size *= 1024*1024*1024

    if d['type'] is None:
        if is_b2():
            return create_label("dos", dest, size, swap)
        else:
            return create_label("dos", dest, size, swap)
    elif d['type'] == 'gpt':
        if wipe:
            # TODO
            return True
        elif is_b2():
            logging.error("Cannot use GPT partitionning format on the Bubba|2")
            return False
        else:
            # TODO
            return True
    elif d['type'] == 'mbr':
        if wipe:
            # TODO
            return True
        else:
            if is_b3():
                logging.warning("Using MBT on the B3 is not recommended (GPT is preferred); continuing anyway")
            # TODO
            return True
