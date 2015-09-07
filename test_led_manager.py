def led_install():
    o = open("/tmp/led_state", 'w')
    o.write('install\n')
    o.close()


def led_error():
    o = open("/tmp/led_state", 'w')
    o.write('error\n')
    o.close()


def led_rescue():
    o = open("/tmp/led_state", 'w')
    o.write('rescue\n')
    o.close()