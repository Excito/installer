__author__ = 'Charles Leclerc'

import daemon
from led_manager import *
import logging
import os
import os.path
from time import sleep
from subprocess import Popen, PIPE
from threading import Thread
import sys


# Early log facility : directly on stdout (meaning the console)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S', level=logging.INFO)

# load and run led control thread
lm = LedManager()
lm.start()
# Fast blink => searching/mounting USB key
lm.set_led(LED_GREEN, 0.1)


# ------------------------------------
# ----- Useful functions -------------
# ------------------------------------

# Run the specified command redirecting output to logging
def runcmd(cmd):
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
    logging.info("[%s] returned status %i" % (','.join(cmd), p.returncode))
    return p.returncode


# Exit the script early due to install key not found/not mounted
# spawn ifplugd with dhcp on both interfaces and exit
def early_exit():
    logging.info("Spawning ifplugd with dhcp on both interfaces")
    logging.info("Updating /etc/network/interfaces")
    net_conf = open('/etc/network/interfaces', 'a')
    net_conf.write("\niface eth0 inet dhcp\niface eth1 inet dhcp\n")
    net_conf.close()
    runcmd(['/etc/init.d/ifplugd', 'start'])
    logging.warning("Install script ended with errors")
    lm.stop(LED_RED)
    lm.join(1)
    logging.shutdown()
    sys.exit(1)


# ------------------------------------
# ----- Main script ------------------
# ------------------------------------

# search and mount USB key
usb_dev = ''
attempts = 5
while attempts:
    logging.info("Searching for USB install key")
    for d in [f for f in os.listdir('/sys/block') if f.startswith('sd')]:
        if 'usb' in os.readlink(os.path.join('/sys/block', d)).split('/'):
            usb_dev = d
            break
    if usb_dev:
        break
    else:
        sleep(2)
    attempts -= 1

if attempts:
    logging.info("Mounting USB install key")
    if not runcmd(['mount', '/dev/%s1' % (usb_dev, ), '/mnt/usb']):
        logging.error('Unable to mount USB key !')
        early_exit()
else:
    logging.error('Unable to detect USB key !')
    early_exit()


def do_install():
    lm.stop()
    lm.join(1)
    logging.shutdown()


with daemon.DaemonContext():
    do_install()

