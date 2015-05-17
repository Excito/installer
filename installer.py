#! /usr/bin/python

__author__ = 'Charles Leclerc'

import daemon
import logging
import os
import os.path
from subprocess import Popen, PIPE
from threading import Thread
import sys
import ConfigParser
import netifaces
from signal import signal, SIGTERM

CONFIG_FILE = '/mnt/usb/install/install.ini'
PID_FILE = '/var/run/installer.pid'

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


def write_pid():
    o = open(PID_FILE, 'w')
    o.write('%i\n' % (os.getpid(),))
    o.close()


def loop_ip_forever():
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


def daemon_term_handler(signum, frame):
    os.unlink(PID_FILE)
    if error:
        led_error()
    else:
        led_rescue()
    sys.exit(0)

# ------------------------------------
# ----- Preliminary script -----------
# ------------------------------------

if os.path.exists(PID_FILE):
    sys.stderr.write('%s exists ; refusing to run !\n' % (PID_FILE, ))
    sys.exit(1)

# Exit the script in early phase due to install key not found/not mounted or no configuration file found
def early_exit():
    global error
    logging.info("Configuring network with default settings")
    configure_network()
    logging.warning("Install script ended with errors")
    logging.shutdown()
    if foreground:
        led_error()
        sys.exit(1)
    else:
        with daemon.DaemonContext():
            error = True
            write_pid()
            signal(SIGTERM, daemon_term_handler)
            loop_ip_forever()
            os.unlink(PID_FILE)
            sys.exit(1)

if is_b2():
    from b2_led_manager import *
else:
    from b3_led_manager import *

led_install()

# Foreground run ?
foreground = len(sys.argv) > 1 and sys.argv[1] == '-f'

if foreground:
    # Everyting to the console
    logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%I:%M:%S',
                        level=logging.INFO)
else:
    # Early log facility in /root folder
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S',
                        level=logging.INFO, filename='/root/install-early.log')

# Configuration defaults
config = ConfigParser.SafeConfigParser()
for s in ('wan', 'lan'):
    config.add_section(s)
    config.set(s, 'proto', 'dhcp')
config.add_section('general')
config.set('general', 'reboot', 'true')

# check if USB key is already mounted, search and mount otherwise
p, t = runcmd2(['cat', '/proc/mounts'])
usb_mounted = False
for iline in p.stdout:
    cc = iline.split()
    if cc[1] == '/mnt/usb':
        usb_mounted = True
t.join()
p.wait()
if usb_mounted:
    logging.info('/mnt/usb already mounted ; skipping USB key detection')
else:
    # search and mount USB key
    usb_dev = ''
    attempts = 5
    while attempts:
        logging.info("Searching for USB install key")
        for d in [f for f in os.listdir('/sys/block') if f.startswith('sd')]:
            if '/usb' in os.readlink(os.path.join('/sys/block', d)):
                usb_dev = d
                break
        if usb_dev:
            break
        else:
            sleep(2)
        attempts -= 1

    if attempts:
        logging.info("Mounting USB install key")
        if runcmd1(['mount', '/dev/%s1' % (usb_dev, ), '/mnt/usb']):
            logging.error('Unable to mount USB key !')
            early_exit()
    else:
        logging.error('Unable to detect USB key !')
        early_exit()

if os.path.exists(CONFIG_FILE):
    logging.info('Loading configuration from ' + CONFIG_FILE)
    if CONFIG_FILE not in config.read(CONFIG_FILE):
        logging.error('Unable to read configuration file !')
        early_exit()
else:
    logging.error('No configuration file found on USB key !')
    early_exit()

configure_network()

if not foreground:
    logging.info("Initialization done. Preparing daemon forking")
    # Logging facility shutdown
    logging.shutdown()
    logging.root.handlers = []


# ------------------------------------
# ----- Main install script ----------
# ------------------------------------

def do_install():
    if not config.has_option('general', 'image'):
        logging.info('No image in configuration. Exiting leaving the rescue system')
        return

if foreground:
    try:
        do_install()
        # we never reboot neither loop with ip in foreground
        led_rescue()
    except:
        logging.exception("Exception in the main function :")
        led_error()
        sys.exit(1)
    finally:
        logging.shutdown()
else:
    with daemon.DaemonContext():
        logging.basicConfig(format='%(asctime)s.%(msecs)d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S',
                            level=logging.INFO, filename="/mnt/usb/install/install.log")
        error = False

        write_pid()
        signal(SIGTERM, daemon_term_handler)

        logging.info("Running installer daemon process with pid %i" % (os.getpid(), ))

        try:
            do_install()
            if config.getboolean('general', 'reboot'):
                os.system('/sbin/reboot')
        except:
            logging.exception("Exception in the main daemon function :")
            error = True
        finally:
            os.unlink(PID_FILE)
            logging.shutdown()

        loop_ip_forever()
        os.unlink(PID_FILE)
