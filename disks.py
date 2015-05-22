__author__ = 'Charles'

import os
import logging
from utils import get_check_conf, getboolean_check_conf, getint_check_conf, InvalidConf, is_b2
import re
import lvm, raid, partitions

target_mout23points = dict()
c_disks = dict()
c_lvm = dict()
c_raid = dict()


def list_sata_disks():
    res = []
    for d in [f for f in os.listdir('/sys/block') if f.startswith('sd')]:
        if '/ata' in os.readlink(os.path.join('/sys/block', d)):
            res.append(d)
    return sorted(res)


def convert_size(sz, ref):
    if sz.lower() == 'remaining':
        return 'remaining'
    elif sz[-1].lower() == 'g':
        try:
            return int(sz[:-1])*1024*1024*1024
        except ValueError:
            logging.error('Invalid size format for %s: %s' % (ref, sz))
            raise InvalidConf
    elif sz[-1].lower() == 'm':
        try:
            return int(sz[:-1])*1024*1024
        except ValueError:
            logging.error('Invalid size format for %s: %s' % (ref, sz))
            raise InvalidConf
    else:
        try:
            return int(sz)
        except ValueError:
            logging.error('Invalid size format for %s: %s' % (ref, sz))
            raise InvalidConf

def parse_partition_reference(d, msg_ref, s_name, accept_raid=False):
    p_raid = '^raid-array\\d+$'
    p_disk = '^disk\\d+-part\\d+$'
    if re.match(p_disk, d):
        di = int(d[4:d.find('-')])
        pi = int(d[d.find('-')+5:])
        return di, pi
    elif accept_raid and re.match(p_raid, d):
        return 0, int(d[10:])
    else:
        if accept_raid:
            logging.error('Invalid format for %s reference in %s (diskX-partY or raid-arrayX '
                          'expected)' % (msg_ref, s_name))
        else:
            logging.error('Invalid format for %s reference in %s (diskX-partY expected)' % (msg_ref, s_name))
        raise InvalidConf

def load_and_check_conf():
    global c_disks
    c_disks.clear()
    logging.info('Loading and checking disk configuration')
    try:
        disks_total = getint_check_conf('disks', 'total', min_value=1, max_value=3 if is_b2() else 2)
        c_disks['u_boot_reconfig'] = getboolean_check_conf('disks', 'u-boot-reconfig', default=False)

        # Partitions
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
                if c_disks[i]['create']:
                    size = get_check_conf(s_name, 'size', default='remaining')
                    c_disks[i][j]['size'] = convert_size(size, s_name)
                    if c_disks[i][j]['size'] == 'remaining' and r_present:
                        logging.error('More than one partitions use "remaining" as size for disk %i !' % (i, ))
                        return False
                    elif c_disks[i][j]['size'] == 'remaining':
                        r_present = True
                if c_disks[i][j]['type'] == 'data':
                    c_disks[i][j]['format'] =\
                        c_disks[i]['create'] or getboolean_check_conf(s_name, 'format', default=True)
                    if c_disks[i][j]['format']:
                        c_disks[i][j]['fs'] = get_check_conf(s_name, 'fs',
                                                             values=['ext2', 'ext3', 'ext4', 'xfs', 'btrfs'])
                    c_disks[i][j]['mountpoint'] = get_check_conf(s_name, 'mountpoint', default='')
                    if not c_disks[i][j]['mountpoint']:
                        del c_disks[i][j]['mountpoint']

        # Software RAID
        total_arrays = getint_check_conf('raid', 'total-arrays', default=0, min_value=0)
        for i in range(1, total_arrays+1):
            s_name = 'raid-array%i' % (i,)
            c_raid[i] = dict()
            c_raid[i]['create'] = getboolean_check_conf(s_name, 'create', default=True)
            if c_raid[i]['create']:
                c_raid[i]['devices'] = []
                for d in [s.strip() for s in get_check_conf(s_name, 'devices').split(',')]:
                    di, pi = parse_partition_reference(d, 'device', s_name)
                    c_raid[i]['devices'].append((di, pi))
            c_raid[i]['type'] = get_check_conf(s_name, 'type', values=['data', 'swap', 'lvm'])
            if c_raid[i]['type'] == 'data':
                c_raid[i]['format'] = c_raid[i]['create'] or getboolean_check_conf(s_name, 'format', default=True)
                if c_raid[i]['format']:
                    c_raid[i]['fs'] = get_check_conf(s_name, 'fs', values=['ext2', 'ext3', 'ext4', 'xfs', 'btrfs'])
                c_raid[i]['mountpoint'] = get_check_conf(s_name, 'mountpoint', default='')
                if not c_raid[i]['mountpoint']:
                    del c_raid[i]['mountpoint']

        # LVM
        total_vg = getint_check_conf('lvm', 'total-vg', default=0, min_value=0)
        for i in range(1, total_vg+1):
            s_name = 'lvm-vg%i' % (i,)
            c_lvm[i] = dict()
            c_lvm[i]['name'] = get_check_conf(s_name, 'name')
            c_lvm[i]['create'] = getboolean_check_conf(s_name, 'create', default=True)
            if c_lvm[i]['create']:
                c_lvm[i]['pv'] = []
                for d in [s.strip() for s in get_check_conf(s_name, 'pv').split(',')]:
                    di, pi = parse_partition_reference(d, 'pv', s_name, True)
                    c_lvm[i]['pv'].append((di, pi))
            c_lvm[i]['lv'] = dict()
            c_lvm[i]['r_present'] = False

        total_lv = getint_check_conf('lvm', 'total-lv', default=0, min_value=0)
        for j in range(1, total_lv+1):
            s_name = 'lvm-lv%i' % (j,)
            name = get_check_conf(s_name, 'name')
            vg_name = get_check_conf(s_name, 'vg').strip()
            for vg_i in c_lvm:
                if c_lvm[i]['name'] == vg_name:
                    break
            if c_lvm[i]['name'] != vg_name:
                logging.error('[%s] Unkwown vg name %s in %s logical volume declaration' % (s_name, vg_name, name))
                raise InvalidConf
            lv = dict()
            lv['create'] = getboolean_check_conf(s_name, 'create', default=True)
            if not lv['create'] and c_lvm[vg_i]['create']:
                logging.error('[%s] Cannot reuse the logical volume %s when the parent volume group %s is being '
                              'created !' % (s_name, name, vg_name))
                return False

            if lv['create']:
                size = get_check_conf(s_name, 'size', default='remaining')
                lv['size'] = convert_size(size, s_name)
                if lv['size'] == 'remaining' and c_lvm[vg_i]['r_present']:
                    logging.error('More than one logical volume to be created in volume group %s (%s) use "remaining" '
                                  'as size !' % (vg_name, c_lvm[vg_i]['name']))
                    return False
                elif lv['size'] == 'remaining':
                    c_lvm[vg_i]['r_present'] = True
            lv['type'] = get_check_conf(s_name, 'type', values=['data', 'swap'])
            if lv['type'] == 'data':
                lv['format'] = lv['create'] or getboolean_check_conf(s_name, 'format', default=True)
                if lv['format']:
                    lv['fs'] = get_check_conf(s_name, 'fs', values=['ext2', 'ext3', 'ext4', 'xfs', 'btrfs'])
                lv['mountpoint'] = get_check_conf(s_name, 'mountpoint', default='')
                if not lv['mountpoint']:
                    del lv['mountpoint']
            c_lvm[vg_i]['lv'][name] = lv
        for i in c_lvm:
            del c_lvm[i]['r_present']
    except InvalidConf:
        return False
