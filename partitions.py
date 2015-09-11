from pkgutil import extend_path
import utils
import logging
from utils import DiskError

__author__ = 'Charles Leclerc <leclerc.charles@gmail.com>'

ext_codes = ['5', 'f', '15', '1f', '22', '42', '85', '91', '9b', 'c5', 'cf', 'd5']


def get_disk_details(dev):
    res = {}
    fdev = '/dev/'+dev
    res['dev'] = fdev
    rc, fd_output = utils.runcmd3(['fdisk', '-l', fdev])
    if rc:
        raise DiskError
    l_type = None
    size = 0
    for iline in fd_output:
        if iline.startswith('Disk %s' % (fdev, )):
            d_size = iline.split()
            size = long(d_size[d_size.index('bytes,')-1])
        elif iline.startswith('Disklabel type'):
            l_type = iline[16:].strip()

    if size == 0:
        logging.error('Unable to read the size of disk %s' % (fdev, ))
        raise DiskError
    else:
        res['size'] = size

    if not l_type:
        res['type'] = None
        res['parts'] = {}
    elif l_type == 'gpt':
        res['type'] = 'gpt'
        res['parts'] = {}
        sec_size = 0
        rc, sg_output = utils.runcmd3(['sgdisk', '-p', fdev])
        if rc:
            raise DiskError
        prec_empty = True
        code_dec = 0
        for iline in sg_output:
            if code_dec > 0:
                n = int(iline.split()[0])
                res['parts'][n] = {}
                fd = '%s%i' % (fdev, n)
                res['parts'][n]['dev'] = fd
                res['parts'][n]['code'] = iline[code_dec:code_dec+4]
                blk = utils.get_blkid_info(fd)
                if 'TYPE' in blk:
                    res['parts'][n]['type'] = blk['TYPE']
            elif len(iline.strip()) == 0:
                prec_empty = True
            elif prec_empty and iline.startswith('Number'):
                code_dec = iline.index('Code')
            elif iline.startswith('Logical sector size:'):
                try:
                    sec_size = int(iline[21:].split()[0])
                except ValueError:
                    logging.exception("Invalid sector size read for %s:" % (dev, ))
                    raise DiskError
                if sec_size not in (512, 4096):
                    logging.error("Invalid sector size read for %s: %s" % (dev, sec_size))
                    raise DiskError
                sec_unit = iline[21:].split()[1]
                if sec_unit != 'bytes':
                    logging.error("Unexpected unit in logical sector size for %s: %s" % (dev, sec_unit))
        for k, v in res['parts'].iteritems():
            rc, sg_output = utils.runcmd3(['sgdisk', "-i", str(k), fdev])
            if rc:
                raise DiskError
            for iline in sg_output:
                if iline.startswith("Partition size:"):
                    v['size'] = sec_size*int(iline[16:].split()[0])

    elif l_type == 'dos':
        res['type'] = 'mbr'
        res['parts'] = {}
        prec_empty = True
        sec_size = 0
        id_dec = 0
        sectors_dec = 0
        for iline in fd_output:
            if len(iline.strip()) == 0:
                prec_empty = True
            elif iline.startswith('Units'):
                cc = iline.split()
                try:
                    sec_size = int(cc[-2])
                except ValueError:
                    logging.exception("Invalid sector size read for %s:" % (dev, ))
                    raise DiskError
                if sec_size not in (512, 4096):
                    logging.error("Invalid sector size read for %s: %s" % (dev, sec_size))
                    raise DiskError
                if cc[-1] != 'bytes':
                    logging.error("Unexpected unit in logical sector size for %s: %s" % (dev, cc[-1]))
            elif prec_empty and iline.startswith('Device'):
                id_dec = iline.index('Id')
                sectors_dec = iline.index('End')+4
            elif id_dec > 0:
                n = int(iline.split()[0][len(fdev):])
                res['parts'][n] = {}
                fd = '%s%i' % (fdev, n)
                res['parts'][n]['dev'] = fd
                res['parts'][n]['id'] = iline[id_dec:id_dec+2].strip().lower()
                res['parts'][n]['size'] = int(iline[sectors_dec:].split()[0]) * sec_size
                blk = utils.get_blkid_info(fd)
                if 'TYPE' in blk:
                    res['parts'][n]['type'] = blk['TYPE']
    else:
        logging.error('Unsupported disklabel type : %s' % (l_type, ))
        raise DiskError
    return res


def check_type(part_num, disk_details, expected):
    if disk_details['type'] == 'mbr':
        if disk_details['parts'][part_num]['id'] in ext_codes:
            logging.error("Will not change partition type of an extended partition !")
            return False
        elif expected == 'data':
            if disk_details['parts'][part_num]['id'] != '83':
                logging.info("Fixing %s partition type" % (disk_details['parts'][part_num]['dev'], ))
                return utils.runcmd2(["sfdisk", "-N%d" % (part_num,), disk_details['dev']], ",,L\n") == 0
        elif expected == 'swap':
            if disk_details['parts'][part_num]['id'] != '82':
                logging.info("Fixing %s partition type" % (disk_details['parts'][part_num]['dev'], ))
                return utils.runcmd2(["sfdisk", "-N%d" % (part_num,), disk_details['dev']], ",,S\n") == 0
    elif disk_details['type'] == 'gpt':
        if expected == 'data':
            if disk_details['parts'][part_num]['code'] != '8300':
                logging.info("Fixing %s partition type" % (disk_details['parts'][part_num]['dev'], ))
                return utils.runcmd2(["sfdisk", "-N%d" % (part_num,), disk_details['dev']], ",,L\n") == 0
        elif expected == 'swap':
            if disk_details['parts'][part_num]['code'] != '8200':
                logging.info("Fixing %s partition type" % (disk_details['parts'][part_num]['dev'], ))
                return utils.runcmd2(["sfdisk", "-N%d" % (part_num,), disk_details['dev']], ",,S\n") == 0
    return True
