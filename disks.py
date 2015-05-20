__author__ = 'Charles'

import os
import logging
from utils import get_check_conf, getboolean_check_conf, getint_check_conf, InvalidConf

c_disks = dict()
c_lvm = dict()
c_raid = dict()


def list_sata_disks():
    res = []
    for d in [f for f in os.listdir('/sys/block') if f.startswith('sd')]:
        if '/ata' in os.readlink(os.path.join('/sys/block', d)):
            res.append(d)
    return sorted(res)


def convert_size(sz):
    if sz.lower() == 'remaining':
        return 'remaining'
    if sz[-1].lower() == 'g':
        try:
            return True, int(sz[:-1])*1024*1024*1024
        except ValueError:
            return False, None
    elif sz[-1].lower() == 'm':
        try:
            return True, int(sz[:-1])*1024*1024
        except ValueError:
            return False, None
    else:
        try:
            return True, int(sz)
        except ValueError:
            return False, None


def load_and_check_conf():
    global c_disks
    c_disks.clear()
    logging.info('Loading and checking disk configuration')
    try:
        disks_total = getint_check_conf('disks', 'total', min_value=1)
        c_disks['u_boot_reconfig'] = getboolean_check_conf('disks', 'u-boot-reconfig', default=False)
        for i in range(1, disks_total+1):
            s_name = 'disk%i' % (i, )
            c_disks[i] = dict()
            c_disks[i]['create'] = getboolean_check_conf(s_name, 'create', default=True)
            disk_total = getint_check_conf(s_name, 'total', min_value=1)
            r_present = False
            for j in range(1, disk_total+1):
                s_name = 'disk%i-part%i' % (i, j)
                c_disks[i][j] = dict()
                c_disks[i][j]['type'] = get_check_conf(s_name, 'type', values=['data', 'lvm', 'raid', 'swap'])
                size = get_check_conf(s_name, 'size', default='remaining')
                c_disks[i][j]['size'] = convert_size(size)
                if c_disks[i][j]['size'] == 'remaining':
                    if r_present:
                        logging.error('More than one partitions use "remaining" as size for disk %i !' % (i, ))
                        return False
                    else:
                        r_present = True
                if c_disks[i][j]['type'] == 'data':
                    c_disks[i][j]['format'] = getboolean_check_conf(s_name, 'format', default=True)
                    if c_disks[i][j]['format']:
                        c_disks[i][j]['fs'] = get_check_conf(s_name, 'fs', values=['ext2', 'ext3', 'ext4',
                                                                                   'xfs', 'btrfs'])
                    c_disks[i][j]['mountpoint'] = get_check_conf(s_name, 'mountpoint', default='')

    except InvalidConf:
        return False
