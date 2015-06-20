__author__ = 'Charles'

import os
import logging
from utils import get_check_conf, getboolean_check_conf, getint_check_conf, InvalidConf, DiskError, is_b2
import re
import lvm
import raid
import partitions

conf_disks = dict()
conf_lvm = dict()
conf_raid = dict()
conf_mountpoints = dict()

disks_details = dict()
lvm_details = dict()
raid_details = dict()

def list_sata_disks():
    res = []
    for d in [f for f in os.listdir('/sys/block') if re.match('sd[a-z]$', f)]:
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

def valid_moutpoint(mp, d):
    global conf_mountpoints
    if mp != '/' and not re.match('(/[a-zA-Z0-9-+.]+)+', mp):
        logging.error('[%s] Invalid mountpoint %s !' % (d, mp))
        raise InvalidConf
    if mp in conf_mountpoints:
        logging.error('[%s] Mountpoint %s already attributed to %s!' % (d, mp, conf_mountpoints[mp]))
        raise InvalidConf
    conf_mountpoints[mp] = d

def load_and_check_conf():
    global conf_disks, conf_lvm, conf_raid, conf_mountpoints
    conf_disks.clear()
    conf_lvm.clear()
    conf_raid.clear()
    conf_mountpoints.clear()
    logging.info('Checking disk configuration')
    phys_raid_map = {}
    phys_lvm_map = {}
    try:
        disks_total = getint_check_conf('disks', 'total', min_value=1, max_value=2)
        sata_disks = list_sata_disks()
        if len(sata_disks) < disks_total:
            logging.error('Not enough disks in the device to apply cconfiguration')
            return False

        # Partitions
        for i in range(1, disks_total+1):
            s_name = 'disk%i' % (i, )
            conf_disks[i] = dict()
            d_name = sata_disks[i-1]
            conf_disks[i]['dev'] = d_name
            conf_disks[i]['create'] = getboolean_check_conf(s_name, 'create', default=True)
            disk_total = getint_check_conf(s_name, 'total', min_value=1)
            r_present = False
            for j in range(1, disk_total+1):
                s_name = 'disk%i-part%i' % (i, j)
                conf_disks[i][j] = dict()
                if not is_b2() or j <= 3:
                    d_name = '%s%s' % (sata_disks[i-1], j)
                else:
                    d_name = '%s%s' % (sata_disks[i-1], j+1)  # logical partition
                conf_disks[i][j]['device'] = d_name
                conf_disks[i][j]['type'] = get_check_conf(s_name, 'type', values=['data', 'lvm', 'raid', 'swap'])
                if conf_disks[i]['create']:
                    size = get_check_conf(s_name, 'size', default='remaining')
                    conf_disks[i][j]['size'] = convert_size(size, s_name)
                    if conf_disks[i][j]['size'] == 'remaining' and r_present:
                        logging.error('More than one partitions use "remaining" as size for disk %i !' % (i, ))
                        return False
                    elif conf_disks[i][j]['size'] == 'remaining':
                        r_present = True
                if conf_disks[i][j]['type'] == 'data':
                    conf_disks[i][j]['format'] =\
                        conf_disks[i]['create'] or getboolean_check_conf(s_name, 'format', default=True)
                    if conf_disks[i][j]['format']:
                        conf_disks[i][j]['fs'] = get_check_conf(s_name, 'fs',
                                                             values=['ext2', 'ext3', 'ext4', 'xfs', 'btrfs'])
                    conf_disks[i][j]['mountpoint'] = get_check_conf(s_name, 'mountpoint', default='')
                    if not conf_disks[i][j]['mountpoint']:
                        del conf_disks[i][j]['mountpoint']
                    else:
                        valid_moutpoint(conf_disks[i][j]['mountpoint'], s_name)
                elif conf_disks[i][j]['type'] == 'raid':
                    phys_raid_map[s_name] = d_name
                elif conf_disks[i][j]['type'] == 'lvm':
                    phys_lvm_map[s_name] = d_name

        # Software RAID
        total_arrays = getint_check_conf('raid', 'total-arrays', default=0, min_value=0)
        for i in range(1, total_arrays+1):
            s_name = 'raid-array%i' % (i,)
            conf_raid[i] = dict()
            conf_raid[i]['create'] = getboolean_check_conf(s_name, 'create', default=True)
            d_name = 'md%i' % (i - 1)
            conf_raid[i]['dev'] = d_name
            if conf_raid[i]['create']:
                conf_raid[i]['devices'] = []
                for d in [s.strip() for s in get_check_conf(s_name, 'devices').split(',')]:
                    if d not in phys_raid_map:
                        logging.error('[%s] Invalid or inexistent device for raid array : %s' % (s_name, d))
                        return False
                    conf_raid[i]['devices'].append(phys_raid_map[d])
            conf_raid[i]['type'] = get_check_conf(s_name, 'type', values=['data', 'swap', 'lvm'])
            if conf_raid[i]['type'] == 'data':
                conf_raid[i]['format'] = conf_raid[i]['create'] or getboolean_check_conf(s_name, 'format', default=True)
                if conf_raid[i]['format']:
                    conf_raid[i]['fs'] = get_check_conf(s_name, 'fs', values=['ext2', 'ext3', 'ext4', 'xfs', 'btrfs'])
                conf_raid[i]['mountpoint'] = get_check_conf(s_name, 'mountpoint', default='')
                if not conf_raid[i]['mountpoint']:
                    del conf_raid[i]['mountpoint']
                else:
                    valid_moutpoint(conf_raid[i]['mountpoint'], s_name)
            elif conf_raid[i]['type'] == 'lvm':
                phys_lvm_map[s_name] = d_name

        # LVM
        total_vg = getint_check_conf('lvm', 'total-vg', default=0, min_value=0)
        for i in range(1, total_vg+1):
            s_name = 'lvm-vg%i' % (i,)
            conf_lvm[i] = dict()
            conf_lvm[i]['name'] = get_check_conf(s_name, 'name')
            conf_lvm[i]['create'] = getboolean_check_conf(s_name, 'create', default=True)
            if conf_lvm[i]['create']:
                conf_lvm[i]['pv'] = []
                for d in [s.strip() for s in get_check_conf(s_name, 'pv').split(',')]:
                    if d not in phys_lvm_map:
                        logging.error('[%s] Invalid physical device %s for volume group %s'
                                      % (s_name, d, conf_lvm[i]['name']))
                        return False
                    conf_lvm[i]['pv'].append(phys_lvm_map[d])
            conf_lvm[i]['lv'] = dict()
            conf_lvm[i]['r_present'] = False

        total_lv = getint_check_conf('lvm', 'total-lv', default=0, min_value=0)
        for j in range(1, total_lv+1):
            s_name = 'lvm-lv%i' % (j,)
            name = get_check_conf(s_name, 'name')
            vg_name = get_check_conf(s_name, 'vg').strip()
            for vg_i in conf_lvm:
                if conf_lvm[i]['name'] == vg_name:
                    break
            if conf_lvm[i]['name'] != vg_name:
                logging.error('[%s] Unkwown vg name %s in %s logical volume declaration' % (s_name, vg_name, name))
                return False
            lv = dict()
            lv['create'] = getboolean_check_conf(s_name, 'create', default=True)
            if not lv['create'] and conf_lvm[vg_i]['create']:
                logging.error('[%s] Cannot reuse the logical volume %s when the parent volume group %s is being '
                              'created !' % (s_name, name, vg_name))
                return False

            if lv['create']:
                size = get_check_conf(s_name, 'size', default='remaining')
                lv['size'] = convert_size(size, s_name)
                if lv['size'] == 'remaining' and conf_lvm[vg_i]['r_present']:
                    logging.error('More than one logical volume to be created in volume group %s (%s) use "remaining" '
                                  'as size !' % (vg_name, conf_lvm[vg_i]['name']))
                    return False
                elif lv['size'] == 'remaining':
                    conf_lvm[vg_i]['r_present'] = True
            lv['type'] = get_check_conf(s_name, 'type', values=['data', 'swap'])
            if lv['type'] == 'data':
                lv['format'] = lv['create'] or getboolean_check_conf(s_name, 'format', default=True)
                if lv['format']:
                    lv['fs'] = get_check_conf(s_name, 'fs', values=['ext2', 'ext3', 'ext4', 'xfs', 'btrfs'])
                lv['mountpoint'] = get_check_conf(s_name, 'mountpoint', default='')
                if not lv['mountpoint']:
                    del lv['mountpoint']
                else:
                    valid_moutpoint(lv['mountpoint'], s_name)
            conf_lvm[vg_i]['lv'][name] = lv
        for i in conf_lvm:
            del conf_lvm[i]['r_present']

    except InvalidConf:
        return False

    return True

def inventory_existing():
    global disks_details, lvm_details, raid_details
    try:
        disks_details = {}
        for dev in list_sata_disks():
            logging.info('Checking /dev/%s' % (dev,))
            disks_details[dev] = partitions.get_disk_details(dev)

        raid.start_all_arrays()

        lvm.start_all_vg()

        raid_details = {}
        for dev in raid.list_raid_arrays():
            logging.info('Checking /dev/%s' % (dev,))
            raid_details[dev] = raid.get_raid_details(dev)

        lvm_details = lvm.get_lvm_details()

    except DiskError:
        return False
    except InvalidConf:
        return False
    finally:
        try:
            lvm.stop_all_vg()
        except:
            pass
        try:
            raid.stop_all_arrays()
        except:
            pass
    return True

def check_existing():
    logging.info(conf_disks.__str__())
    logging.info(disks_details.__str__())
    for i in [i for i in conf_disks if not conf_disks[i]['create']]:
        logging.info('Checking consistency for kept disk%i' % (i, ))
        logging.info(conf_disks[i].__str__())
        for j in [j for j in conf_disks[i] if j.isdigit()]:
            pass


def needs_uboot_reconfig():
    pass
