__author__ = 'Charles Leclerc <leclerc.charles@gmail.com>'

FREQ_SLOW = 32768
FREQ_MEDIUM = 16384
FREQ_QUICK = 8192


def b2_set_freq(freq):
    c = open('/sys/devices/platform/bubbatwo/ledfreq', 'w')
    c.write(str(freq))
    c.close()


def b2_set_blink():
    l = open('/sys/devices/platform/bubbatwo/ledmode', 'w')
    l.write("blink")
    l.close()


def led_install():
    b2_set_freq(FREQ_QUICK)
    b2_set_blink()


def led_error():
    b2_set_freq(FREQ_SLOW)
    b2_set_blink()


def led_rescue():
    b2_set_freq(FREQ_MEDIUM)
    b2_set_blink()