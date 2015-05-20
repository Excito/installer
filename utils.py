
from subprocess import Popen, PIPE
from threading import Thread
import netifaces
import logging
import os.path
from ConfigParser import NoOptionError, NoSectionError

config = None

class InvalidConf(Exception):
    pass

# ------------------------------------
# ----- Useful functions -------------
# ------------------------------------

# Run the specified command redirecting all output to logging
# Returns the command return code
def runcmd1(cmd):
    logging.info("Running [%s]" % (','.join(cmd)))
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)

    def follow_stderr():
        for eline in p.stderr:
            logging.error(eline)

    t = Thread(target=follow_stderr)
    t.start()
    for iline in p.stdout:
        logging.info(iline)
    t.join()
    p.wait()
    if p.returncode:
        logging.error("[%s] returned status %i" % (','.join(cmd), p.returncode))
    else:
        logging.info("[%s] returned status %i" % (','.join(cmd), p.returncode))
    return p.returncode


# Run the specified command redirecting only stderr to logging
# Returns the process reference and the stderr writing thread
def runcmd2(cmd):
    logging.info("Running [%s]" % (','.join(cmd)))
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)

    def follow_stderr():
        for eline in p.stderr:
            logging.error(eline)

    t = Thread(target=follow_stderr)
    t.start()
    return p, t


# write /etc/network/interfaces from configuration
def configure_network():
    global config
    logging.info('Writing /etc/network/interfaces')
    o = open('/etc/network/interfaces', 'a')
    for s, i in (('wan', 'eth0'), ('lan', 'eth1')):
        p = config.get(s, 'proto').strip()
        if p == 'static' and (not config.has_option(s, 'ipaddr') or not config.has_option(s, 'netmask')):
            logging.warning('Missing ipaddr or netmask for static configuration of %s ; falling back to DHCP' % (s, ))
            p = 'dhcp'
        o.write('\niface %s proto %s' % (i, p))
        if p == 'static':
            o.write('\n  address %s\n  netmask  %s' % (config.get(s, 'ipaddr').strip(),
                                                       config.get(s, 'netmask').strip()))
            if config.has_option(s, 'gateway'):
                o.write('\n  gateway %s' % (config.get(s, 'gateway').strip()))
        o.write('\n')
    o.close()


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


# Detect if we're running on a Bubba|2 (if not we're on a B3)
def is_b2():
    return os.path.exists('/sys/devices/platform/bubbatwo')


if is_b2():
    from b2_led_manager import *
else:
    from b3_led_manager import *


def loop_ip_forever(error=False):
    if is_b2():
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
    if max_value and res > min_value:
        logging.error('Invalid integer value for %s in section %s (maximum value: %i)' % (option, section, max_value))
        raise InvalidConf('Invalid integer value for %s in section %s (maximum value: %i)'
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
