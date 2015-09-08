import os
import logging
from subprocess import Popen, PIPE
from threading import Thread
from utils import InvalidConf, DiskError, is_b2, is_b3
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


def create_mbr(d, size):
    logging.info("Creating MBR structure and first %s size partition on %s" % (size, d))
    p = Popen(["fdisk", "/dev/%s" % (d, )], stdin=PIPE, stdout=PIPE, stderr=PIPE)

    def follow_stderr():
        for eline in p.stderr:
            logging.error('[cmd] '+eline.strip())

    t = Thread(target=follow_stderr)
    t.start()
    for iline in p.stdout:
        logging.info('[cmd] '+iline.strip())
    t.join()


def create_gpt(d, size):
    pass


def prepare_disk(wipe, size, dest):
    d = disks_details[dest]
    if d['type'] is None:
        if d['size'] - 10*1024*1024 < size:
            logging.error("Destination disk is too small !")
            return False
        if is_b2():
            return create_mbr(dest, size)
        else:
            return create_gpt(dest, size)
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
