#! /usr/bin/python

__author__ = 'Charles Leclerc'

import daemon
import os.path
import logging
import sys
import ConfigParser
from signal import signal, SIGTERM

import utils
import disks

CONFIG_FILE = '/mnt/usb/install/install.ini'
PID_FILE = '/var/run/installer.pid'


def write_pid():
    o = open(PID_FILE, 'w')
    o.write('%i\n' % (os.getpid(),))
    o.close()

def remove_pid():
    if os.path.exists(PID_FILE):
        os.unlink(PID_FILE)

def daemon_term_handler(signum, frame):
    global error
    remove_pid()
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
    if not foreground:
        logging.info("Configuring network with default settings")
        utils.configure_network()
    logging.warning("Install script ended with errors")
    logging.shutdown()
    if foreground:
        led_error()
        sys.exit(1)
    else:
        with daemon.DaemonContext():
            write_pid()
            signal(SIGTERM, daemon_term_handler)
            utils.loop_ip_forever(True)
            remove_pid()
            sys.exit(1)

if utils.is_b2():
    from b2_led_manager import *
else:
    from b3_led_manager import *

led_install()

# Foreground run ?
foreground = len(sys.argv) > 1 and sys.argv[1] == '-f'

if foreground:
    # Everyting to the console
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S',
                        level=logging.INFO)
else:
    # Early log facility in /root folder
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO, filename='/root/install-early.log')

# Configuration defaults
config = ConfigParser.SafeConfigParser()
utils.config = config

for s in ('wan', 'lan'):
    config.add_section(s)
    config.set(s, 'proto', 'dhcp')
config.add_section('general')
config.set('general', 'reboot', 'true')

# check if USB key is already mounted, search and mount otherwise
rc, output = utils.runcmd2(['cat', '/proc/mounts'])
usb_mounted = False
for iline in output:
    cc = iline.split()
    if cc[1] == '/mnt/usb':
        usb_mounted = True

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
        if utils.runcmd1(['mount', '/dev/%s1' % (usb_dev, ), '/mnt/usb']):
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

if not foreground:
    utils.configure_network()

if not foreground:
    logging.info("Initialization done. Preparing daemon forking")
    # Logging facility shutdown
    logging.shutdown()
    logging.root.handlers = []


# ------------------------------------
# ----- Main install script ----------
# ------------------------------------

def do_install():
    global error, config
    u_boot_reconfig = utils.getboolean_check_conf('general', 'u-boot-reconfig', False)
    if not disks.load_and_check_conf():
        error = True
        return
    if not disks.verify_existing():
        error = True
        return
    if disks.needs_uboot_reconfig() and not u_boot_reconfig:
        logging.error('Chosen disk configuration needs U-Boot configuration change, yet u-boot-reconfig is False')
        error = True
        return


if foreground:
    try:
        error = False
        if config.has_option('general', 'image'):
            do_install()
        else:
            logging.info('No image in configuration. Exiting leaving the rescue system')
        # we never reboot neither loop with ip in foreground
        if error:
            led_error()
        else:
            led_rescue()
    except:
        logging.exception("Exception in the main function :")
        led_error()
        sys.exit(1)
    finally:
        logging.shutdown()
    sys.exit(0)
else:
    with daemon.DaemonContext():
        logging.basicConfig(format='%(asctime)s.%(msecs)d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S',
                            level=logging.INFO, filename="/mnt/usb/install/install.log")
        error = False

        write_pid()
        signal(SIGTERM, daemon_term_handler)

        logging.info("Running installer daemon process with pid %i" % (os.getpid(), ))

        try:
            if config.has_option('general', 'image'):
                do_install()
                if not error and config.getboolean('general', 'reboot'):
                    os.system('/sbin/reboot')
            else:
                logging.info('No image in configuration. Exiting leaving the rescue system')
        except:
            logging.exception("Exception in the main daemon function :")
            error = True
        finally:
            os.unlink(PID_FILE)
            logging.shutdown()

        utils.loop_ip_forever(error)
        os.unlink(PID_FILE)
