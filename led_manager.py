from time import time
from threading import Event, Thread
import logging

LED_BLUE = 0
LED_RED = 1
LED_GREEN = 2
LED_CYAN = 3
LED_PURPLE = 4
LED_YELLOW = 5
LED_WHITE = 6


class LedState:

    def __init__(self):
        self.color = LED_GREEN
        self.lit = True
        self.interval = 0
        self.last_change = 0


class LedManager(Thread):

    def __init__(self):
        Thread.__init__(self, name="led_manager")
        self.req = Event()
        self.c_state = LedState()
        self.n_state = LedState()
        self.running = True

    def set_led(self, color, interval=0):
        self.n_state.color = color
        self.n_state.interval = interval
        self.req.set()

    def stop(self, color=LED_GREEN):
        self.running = False
        self.n_state.color = color
        self.req.set()

    def run(self):
        while self.running:
            if self.c_state.interval > 0:
                wt = self.c_state.last_change - time() + self.c_state.interval
                if wt > 0:
                    self.req.wait(wt)
            else:
                self.req.wait()

            if not self.running:
                break
            elif self.req.isSet():
                self.req.clear()
            elif self.c_state.interval == 0:
                continue
            self.update_led()
        self.n_state.interval = 0
        self.n_state.lit = True
        self.update_led()

    def update_led(self):
        logging.debug('update_led c_state(%i %s %f) n_state(%i %s %f)' % (self.c_state.color, self.c_state.lit,
                                                                          self.c_state.interval, self.n_state.color,
                                                                          self.n_state.lit, self.n_state.interval))
        if self.n_state.lit:
            if self.n_state.color != self.c_state.color:
                self.set_color(self.n_state.color)
                if not self.c_state.lit:
                    self.set_lit()
                if self.n_state.interval > 0:
                    self.c_state.interval = self.n_state.interval
                    self.c_state.last_change = time()
            elif self.n_state.interval > 0:
                self.c_state.interval = self.n_state.interval
                if self.c_state.lit:
                    self.set_off()
                else:
                    self.set_lit()
                self.c_state.last_change = time()
            elif not self.c_state.lit:
                self.set_lit()
        elif self.c_state.lit:
            self.set_off()

    def set_color(self, color):
        c = open('/sys/devices/platform/bubbatwo/color', 'w')
        c.write(str(self.n_state.color))
        c.close()
        self.c_state.color = color

    def set_lit(self):
        l = open('/sys/devices/platform/bubbatwo/ledmode', 'w')
        l.write("lit")
        l.close()
        self.c_state.lit = True

    def set_off(self):
        l = open('/sys/devices/platform/bubbatwo/ledmode', 'w')
        l.write("off")
        l.close()
        self.c_state.lit = False

# Test code
if __name__ == '__main__':
    lm = LedManager()
    lm.start()
    a = raw_input()
    lm.set_led(LED_GREEN, 0.1)
    a = raw_input()
    lm.set_led(LED_BLUE, 0)
    a = raw_input()
    lm.set_led(LED_YELLOW, 0.3)
    a = raw_input()
    lm.stop()
    lm.join()