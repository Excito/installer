from time import sleep

__author__ = 'Charles Leclerc <leclerc.charles@gmail.com>'

def b3_set_color(color):
    r = 0
    g = 0
    b = 0
    if color == 'red':
        r = 1
    elif color == 'green':
        g = 1
    elif color == 'blue':
        b = 1
    elif color == 'cyan':
        b, g = 1, 1
    elif color == 'yellow':
        r, g = 1, 1
    elif color == 'purple':
        r, b = 1, 1
    elif color == 'white':
        r, g, b = 1, 1, 1

    r_f = open('/sys/class/leds/bubba3:red:error/brightness', 'w')
    r_f.write(str(r))
    r_f.close()

    g_f = open('/sys/class/leds/bubba3:green:programming/brightness', 'w')
    g_f.write(str(g))
    g_f.close()

    b_f = open('/sys/class/leds/bubba3:blue:active/brightness', 'w')
    b_f.write(str(b))
    b_f.close()


def led_install():
    b3_set_color('cyan')


def led_error():
    b3_set_color('red')


def led_rescue():
    b3_set_color('green')


def b3_print_integer(n):
    for i in n:
        i = int(i)
        if i == 0:
            b3_set_color('purple')
            sleep(0.2)
            b3_set_color('black')
            sleep(0.2)

        while i > 0:
            b3_set_color('yellow')
            sleep(0.2)
            b3_set_color('black')
            sleep(0.2)
            i -= 1
        sleep(0.3)
