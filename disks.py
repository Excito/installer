import os
import logging
from utils import InvalidConf, DiskError
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


def inventory_disks():
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
