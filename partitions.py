__author__ = 'Charles'

import utils
import logging
from utils import DiskError


def get_disk_details(dev):
    res = {}
    fdev = '/dev/'+dev
    res['dev'] = fdev
    rc, fd_output = utils.runcmd2(['fdisk', '-l', fdev])
    if rc:
        raise DiskError
    l_type = None
    for iline in fd_output:
        if iline.startswith('Disklabel type'):
            l_type = iline[16:].strip()

    if not l_type:
        logging.error('Unable to parse disklabel type ??!!??')
        raise DiskError
    elif l_type == 'gpt':
        res['type'] = 'gpt'
        res['parts'] = {}
        rc, sg_output = utils.runcmd2(['sgdisk', '-p', fdev])
        prec_empty = True
        code_dec = 0
        for iline in sg_output:
            if len(iline.strip()) == 0:
                prec_empty = True
            elif prec_empty and iline.startswith('Number'):
                code_dec = iline.index('Code')
            elif code_dec > 0:
                n = int(iline.split()[0])
                res['parts'][n] = {}
                fd = '%s%i' % (fdev, n)
                res['parts'][n]['dev'] = fd
                res['parts'][n]['code'] = iline[code_dec:code_dec+4]
                blk = utils.get_blkid_info(fd)
                if 'TYPE' in blk:
                    res['parts'][n]['type'] = blk['TYPE']
    elif l_type == 'dos':
        res['type'] = 'mbr'
        res['parts'] = {}
        prec_empty = True
        id_dec = 0
        n = 1
        for iline in fd_output:
            if len(iline.strip()) == 0:
                prec_empty = True
            elif prec_empty and iline.startswith('Device'):
                id_dec = iline.index('Id')
            elif id_dec > 0:
                res['parts'][n] = {}
                fd = '%s%i' % (fdev, n)
                res['parts'][n]['dev'] = fd
                res['parts'][n]['id'] = iline[id_dec:id_dec+2].strip()
                blk = utils.get_blkid_info(fd)
                if 'TYPE' in blk:
                    res['parts'][n]['type'] = blk['TYPE']
                n += 1
    else:
        logging.error('Unsupported disklabel type : %s' % (l_type, ))
        raise DiskError
    return res
