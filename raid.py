__author__ = 'Charles'

import utils
import os
import re


def list_raid_arrays():
    res = [f for f in os.listdir('/sys/block') if re.match('md[0-9]+$', f)]
    return sorted(res)


def start_all_arrays():
    utils.runcmd1(['mdadm', '--assemble', '--scan'], err_to_out=True)


def stop_all_arrays():
    error = False
    for d in list_raid_arrays():
        if utils.runcmd1(['mdadm', '--stop', '/dev/%s' % (d, )], err_to_out=True):
            error = True
    if error:
        raise utils.DiskError


def get_raid_details(dev):
    res = {}
    sys_root = '/sys/block/%s' % (dev, )
    res['metadata_version'] = open('%s/md/metadata_version' % (sys_root, ), 'r').read().strip()
    res['devices'] = os.listdir('%s/slaves' % (sys_root, ))
    res['level'] = int(open('%s/md/level' % (sys_root, ), 'r').read().strip()[4:])
    blk = utils.get_blkid_info('/dev/%s' % (dev, ))
    if 'TYPE' in blk:
        res['type'] = blk['TYPE']
    return res
