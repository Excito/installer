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

# ------------------------------------
# ----- Preliminary script -----------
# ------------------------------------

# Exit the script in early phase due to install key not found/not mounted
# spawn ifplugd with dhcp on both interfaces and exit
def early_exit():
    logging.info("Spawning ifplugd with dhcp on both interfaces")
    logging.info("Updating /etc/network/interfaces")
#    net_conf = open('/etc/network/interfaces', 'a')
#    net_conf.write("\niface eth0 inet dhcp\niface eth1 inet dhcp\n")
#    net_conf.close()
#    runcmd(['/etc/init.d/ifplugd', 'start'])
    logging.warning("Install script ended with errors")
    lm1.stop(LED_RED)
    lm1.join(1)
    logging.shutdown()
    sys.exit(1)

# Early log facility : directly on stdout (meaning the console)
logging.basicConfig(format='%(asctime)s.%(msecs)d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S',
                    level=logging.INFO)

# load and run early led control thread (which will be stopped before forking and restarted after)
lm1 = LedManager()
lm1.start()
# Fast blink => searching/mounting USB key
lm1.set_led(LED_GREEN, 0.1)

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

logging.info("Initialization done. Preparing daemon forking")

# Stopping led manager thread (can't support the fork)
lm1.stop()
lm1.join()

# Logging facility shutdown
logging.shutdown()
logging.root.handlers = []

# ------------------------------------
# ----- Main install script ----------
# ------------------------------------

def do_install():
    lm2.set_led(LED_CYAN)
    env_out = open("/mnt/usb/install/env.txt", 'w')
    p, t = runcmd2(['fw_printenv', 'ethaddr', 'eth1addr', 'key'])
    for iline in p.stdout:
        env_out.write(iline)
    t.join()
    p.wait()
    os.system("/sbin/reboot")

with daemon.DaemonContext():
    logging.basicConfig(format='%(asctime)s.%(msecs)d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S',
                    level=logging.INFO, filename="/mnt/usb/install/install.log")
    logging.info("Running installer daemon process")
    logging.info("Restarting led manager ...")
    lm2 = LedManager()
    lm2.start()
    try:
        do_install()
        lm2.stop(LED_GREEN)
    except:
        logging.exception("Exception in the main daemon function :")
        lm2.stop(LED_RED)
    finally:
        logging.shutdown()

