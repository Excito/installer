from subprocess import Popen, PIPE, STDOUT
from threading import Thread
import netifaces
import logging
import os.path
from ConfigParser import NoOptionError, NoSectionError
import shlex


config = None


class InvalidConf(Exception):
    pass


class DiskError(Exception):
    pass


# ------------------------------------
# ----- Useful functions -------------
# ------------------------------------

# Run the specified command redirecting all output to logging
# Returns the command return code
def runcmd1(cmd, ign_out=False, ign_err=False, err_to_out=False):
    logging.info("Running '%s'" % (" ".join(cmd)))
    if ign_out and ign_err:
        p = Popen(cmd, stdout=open('/dev/null', 'w'), stderr=STDOUT)
    elif ign_out:
        p = Popen(cmd, stdout=open('/dev/null', 'w'), stderr=PIPE)
        for eline in p.stderr:
            logging.error('['+cmd[0]+'] '+eline.strip())
    elif ign_err:
        p = Popen(cmd, stdout=PIPE, stderr=open('/dev/null', 'w'))
        for iline in p.stdout:
            logging.info('['+cmd[0]+'] '+iline.strip())
    elif err_to_out:
        p = Popen(cmd, stdout=PIPE, stderr=STDOUT)
        for iline in p.stdout:
            logging.info('['+cmd[0]+'] '+iline.strip())
    else:
        p = Popen(cmd, stdout=PIPE, stderr=PIPE)

        def follow_stderr():
            for eline in p.stderr:
                logging.error('['+cmd[0]+'] '+eline.strip())

        t = Thread(target=follow_stderr)
        t.start()
        for iline in p.stdout:
            logging.info('['+cmd[0]+'] '+iline.strip())
        t.join()

    p.wait()

    return p.returncode


# Run the specified command with specified input redirecting all output to logging
# Returns the command return code
def runcmd2(cmd, cmd_input, ign_out=False, ign_err=False, err_to_out=False):
    logging.info("Running '%s' with this input: %s" % (" ".join(cmd), cmd_input.replace("\n", "|")))
    if ign_out and ign_err:
        p = Popen(cmd, stdin=PIPE, stdout=open('/dev/null', 'w'), stderr=STDOUT)
        p.stdin.write(cmd_input)
        p.stdin.close()
    elif ign_out:
        p = Popen(cmd, stdin=PIPE, stdout=open('/dev/null', 'w'), stderr=PIPE)
        p.stdin.write(cmd_input)
        p.stdin.close()
        for eline in p.stderr:
            logging.error('['+cmd[0]+'] '+eline.strip())
    elif ign_err:
        p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=open('/dev/null', 'w'))
        p.stdin.write(cmd_input)
        p.stdin.close()
        for iline in p.stdout:
            logging.info('['+cmd[0]+'] '+iline.strip())
    elif err_to_out:
        p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=STDOUT)
        p.stdin.write(cmd_input)
        p.stdin.close()
        for iline in p.stdout:
            logging.info('['+cmd[0]+'] '+iline.strip())
    else:
        p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        p.stdin.write(cmd_input)
        p.stdin.close()

        def follow_stderr():
            for eline in p.stderr:
                logging.error('['+cmd[0]+'] '+eline.strip())

        t = Thread(target=follow_stderr)
        t.start()
        for iline in p.stdout:
            logging.info('['+cmd[0]+'] '+iline.strip())
        t.join()

    p.wait()

    return p.returncode


# Run the specified command redirecting only stderr to logging
# Returns the process returncode and the complete output (array containing lines)
def runcmd3(cmd, ign_err=False):
    logging.info("Running '%s'" % (" ".join(cmd)))
    output = []
    if ign_err:
        p = Popen(cmd, stdout=PIPE, stderr=open('/dev/null', 'w'))
        for iline in p.stdout:
            output.append(iline)
    else:
        p = Popen(cmd, stdout=PIPE, stderr=PIPE)

        def follow_stderr():
            for eline in p.stderr:
                logging.error('['+cmd[0]+'] '+eline.strip())

        t = Thread(target=follow_stderr)
        t.start()
        for iline in p.stdout:
            output.append(iline)
        t.join()
    p.wait()
    return p.returncode, output


# write /etc/network/interfaces from configuration
def configure_network():
    global config
    logging.info('Writing /etc/network/interfaces')
    with open('/etc/network/interfaces', 'a') as o:
        o.write(gen_network_config())
    if config.has_option('dns', 'nameservers') or config.has_option('dns', 'search'):
        logging.info('Writing /etc/resolv.conf')
        with open('/etc/resolv.conf', 'w') as o:
            for ns in get_check_conf('dns', 'nameservers', '').split(','):
                o.write('nameserver %s\n' % (ns, ))
            if config.has_option('dns', 'search'):
                o.write('search %s\n' % (config.get('dns', 'search'), ))


def gen_network_config():
    global config
    res = ''
    for s, i in (('wan', 'eth0'), ('lan', 'eth1')):
        res += '\nallow-hotplug %s' % (i, )
        p = config.get(s, 'proto').strip()
        if p == 'static' and (not config.has_option(s, 'ipaddr') or not config.has_option(s, 'netmask')):
            logging.warning('Missing ipaddr or netmask for static configuration of %s ; falling back to DHCP' % (s, ))
            p = 'dhcp'
        res += '\niface %s inet %s' % (i, p)
        if p == 'static':
            res += '\n  address %s\n  netmask  %s' % (config.get(s, 'ipaddr').strip(), config.get(s, 'netmask').strip())
            if config.has_option(s, 'gateway'):
                res += '\n  gateway %s' % (config.get(s, 'gateway').strip())
        res += '\n'
    return res


# Return the relevant numbers from the first address ip found on eth0/eth1
# class C : last number; class B : last two numbers, etc.
def get_first_ip_relevant_numbers():
    for i in 'eth0', 'eth1':
        addrs = netifaces.ifaddresses(i)
        if netifaces.AF_INET not in addrs:
            continue
        if len(addrs[netifaces.AF_INET]) >= 1 and 'addr' in addrs[netifaces.AF_INET][0]:
            ip = addrs[netifaces.AF_INET][0]['addr'].split('.')
            nm = addrs[netifaces.AF_INET][0]['netmask'].split('.')
            res = []
            for r, n in map(None, ip, nm):
                if n == '0':
                    res.append(r)
            return res
    return None


# Detect if we're running on a Bubba|2
def is_b2():
    return os.path.exists('/sys/devices/platform/bubbatwo')


# Detect if we're running on a B3
def is_b3():
    return os.path.exists('/sys/class/leds/bubba3:blue:active')

if is_b2():
    from b2_led_manager import *
elif is_b3():
    from b3_led_manager import *
else:
    from test_led_manager import *


def loop_ip_forever(error=False):
    if not is_b3():
        if error:
            led_error()
        else:
            led_rescue()
        return  # not supported on the b2
    ip = None
    while True:
        if error:
            led_error()
        else:
            led_rescue()
        sleep(2)
        if not ip:
            ip = get_first_ip_relevant_numbers()
        if ip:
            first = True
            for n in ip:
                if first:
                    first = False
                else:
                    b3_set_color('cyan')
                    sleep(1)
                b3_set_color('black')
                sleep(0.5)
                b3_print_integer(n)
            sleep(0.2)


def get_check_conf(section, option, default=None, values=[]):
    global config
    try:
        res = config.get(section, option)
    except NoSectionError:
        if default is not None:
            return default
        else:
            logging.error('%s section missing !' % (section, ))
            raise InvalidConf('%s section missing !' % (section, ))
    except NoOptionError:
        if default is not None:
            return default
        else:
            logging.error('%s value missing from section %s !' % (option, section))
            raise InvalidConf('%s value missing from section %s!' % (option, section))
    if values and res not in values:
        logging.error('Invalid value for %s in section %s (possible values: %s)' % (option, section, ','.join(values)))
        raise InvalidConf('Invalid value for %s in section %s (possible values: %s)'
                          % (option, section, ','.join(values)))
    return res


def getint_check_conf(section, option, default=None, min_value=None, max_value=None):
    global config
    try:
        res = config.getint(section, option)
    except NoSectionError:
        if default is not None:
            return default
        else:
            logging.error('%s section missing !' % (section, ))
            raise InvalidConf('%s section missing !' % (section, ))
    except NoOptionError:
        if default is not None:
            return default
        else:
            logging.error('%s value missing from section %s!' % (option, section))
            raise InvalidConf('%s value missing from section %s!' % (option, section))
    except ValueError:
        logging.error('Malformed integer value for %s in section %s' % (option, section))
        raise InvalidConf('Malformed integer value for %s in section %s' % (option, section))
    if min_value and res < min_value:
        logging.error('Invalid integer value for %s in section %s (minimum value: %i)' % (option, section, min_value))
        raise InvalidConf('Invalid integer value for %s in section %s (minimum value: %i)'
                          % (option, section, min_value))
    if max_value and res > max_value:
        logging.error('Invalid integer value for %s in section %s (maximum value: %i)' % (option, section, max_value))
        raise InvalidConf('Invalid integer value for %s in section %s (maximum value: %i)'
                          % (option, section, max_value))
    return res


def getfloat_check_conf(section, option, default=None, min_value=None, max_value=None):
    global config
    try:
        res = config.getfloat(section, option)
    except NoSectionError:
        if default is not None:
            return default
        else:
            logging.error('%s section missing !' % (section, ))
            raise InvalidConf('%s section missing !' % (section, ))
    except NoOptionError:
        if default is not None:
            return default
        else:
            logging.error('%s value missing from section %s!' % (option, section))
            raise InvalidConf('%s value missing from section %s!' % (option, section))
    except ValueError:
        logging.error('Malformed float value for %s in section %s' % (option, section))
        raise InvalidConf('Malformed float value for %s in section %s' % (option, section))
    if min_value and res < min_value:
        logging.error('Invalid float value for %s in section %s (minimum value: %i)' % (option, section, min_value))
        raise InvalidConf('Invalid float value for %s in section %s (minimum value: %i)'
                          % (option, section, min_value))
    if max_value and res > max_value:
        logging.error('Invalid float value for %s in section %s (maximum value: %i)' % (option, section, max_value))
        raise InvalidConf('Invalid float value for %s in section %s (maximum value: %i)'
                          % (option, section, max_value))
    return res


def getboolean_check_conf(section, option, default=None):
    global config
    try:
        return config.getboolean(section, option)
    except NoSectionError:
        if default is not None:
            return default
        else:
            logging.error('%s section missing !' % (section, ))
            raise InvalidConf('%s section missing !' % (section, ))
    except NoOptionError:
        if default is not None:
            return default
        else:
            logging.error('%s value missing from section %s!' % (option, section))
            raise InvalidConf('%s value missing from section %s!' % (option, section))
    except ValueError:
        logging.error('Malformed booleam value for %s in section %s' % (option, section))
        raise InvalidConf('Malformed boolean value for %s in section %s' % (option, section))


def get_blkid_info(dev):
    rc, output = runcmd3(['blkid', dev], True)
    res = {}
    if output:
        l = output[0]
        for var in shlex.split(l[len(dev)+2:]):
            kv = var.split('=')
            if kv[1] == 'LVM2_member':
                kv[1] = 'lvm'
            res[kv[0]] = kv[1]
    return res


def sizeof_fmt(num, suffix='B'):
    if num == 'full':
        return num
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)
