#! /usr/bin/python

import daemon
import os.path
import logging
import sys
import ConfigParser
from signal import signal, SIGTERM

import utils
import disks

__author__ = 'Charles Leclerc <leclerc.charles@gmail.com>'

CONFIG_FILE = '/mnt/usb/install/install.ini'
LOG_FILE = '/mnt/usb/install/install.log'
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
elif utils.is_b3():
    from b3_led_manager import *
else:
    from test_led_manager import *

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

if not (utils.is_b3() or utils.is_b2()):
    logging.info('Test environment ; using config from installer directory')
    CONFIG_FILE = '/opt/excito/install-test.ini'
    LOG_FILE = '/opt/excito/install-test.log'


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
    logging.info("Initialization done. Preparing daemon forking")
    # Logging facility shutdown
    logging.shutdown()
    logging.root.handlers = []


# ------------------------------------
# ----- Main install script ----------
# ------------------------------------

def do_install():
    global error, config

    if not disks.inventory_existing():
        error = True
        return

    if len(disks.disks_details) == 0:
        logging.error("No SATA disk found !")
        error = True
        return

    dest = disks.disks_details.keys()[0]
    sz = utils.getint_check_conf('general', 'size', 10)*1024*1024*1024
    logging.info("Destination disk: %s (%s)" % (dest, utils.sizeof_fmt(disks.disks_details[dest]['size'])))

    if not disks.prepare_disk(utils.getboolean_check_conf('general', 'wipe', False), sz, dest):
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
        logging.exception("Exception in the main install function :")
        led_error()
        sys.exit(1)
    finally:
        logging.shutdown()
    sys.exit(0)
else:
    with daemon.DaemonContext():
        write_pid()
        signal(SIGTERM, daemon_term_handler)

        logging.basicConfig(format='%(asctime)s.%(msecs)d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S',
                            level=logging.INFO, filename=LOG_FILE)

        logging.info("Running installer daemon process with pid %i" % (os.getpid(), ))

        error = False

        if config.has_option('general', 'image'):
            try:
                do_install()
            except:
                logging.exception("Exception in the main install function :")
                error = True
            if not error and utils.getboolean_check_conf('general', 'reboot', 'true'):
                logging.info('install done; rebooting system')
                os.system('/sbin/reboot')
                logging.shutdown()
                os.unlink(PID_FILE)
                sys.exit(0);
            else:
                utils.loop_ip_forever(error)
        else:
            logging.info('No image in configuration. Exiting leaving the rescue system')
            utils.loop_ip_forever(error)
            os.unlink(PID_FILE)
