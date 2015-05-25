__author__ = 'Charles'

import utils
import os.path
import logging

def start_all_vg():
    if utils.runcmd1(['vgchange', '-ay']):
        logging.error('Unable to activate volume groups !')
        raise utils.DiskError

def stop_all_vg():
    if utils.runcmd1(['vgchange', '-an']):
        logging.error('Unable to deactivate volume groups !')
        raise utils.DiskError

def get_lvm_details():
    res = {}
    rc, output = utils.runcmd2(['vgs', '--noheadings', '-o', 'vg_name'])
    if rc:
        raise utils.DiskError
    for l in output:
        n = l.strip()
        res[n] = {}
        res[n]['pv'] = []
        res[n]['lv'] = []
    rc, output = utils.runcmd2(['vgs', '--noheadings', '-o', 'vg_name,pv_name'])
    if rc:
        raise utils.DiskError
    for l in output:
        f = l.split()
        res[f[0]]['pv'].append(f[1].split('/')[-1])
    rc, output = utils.runcmd2(['vgs', '--noheadings', '-o', 'vg_name,lv_name'])
    if rc:
        raise utils.DiskError
    for l in output:
        f = l.split()
        res[f[0]]['lv'].append({'name': f[1]})

    for vg_name in res:
        for lv in res[vg_name]['lv']:
            dev = '/dev/mapper/%s-%s' % (vg_name, lv['name'])
            if not os.path.exists(dev):
                logging.error('Unable to find the device %s !!??!!' % (dev, ))
                raise utils.DiskError
            blk = utils.get_blkid_info(dev)
            if 'TYPE' in blk:
                lv['type'] = blk['TYPE']

    return res

