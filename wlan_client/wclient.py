# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-09 

__updated__ = "2021-02-09"
__version__ = "0.1"

import gc
import time
from machine import Pin
from micropython import const
from wlan_link_libs.frames import Frames
from wlan_link_libs.uart import WUart
from wlan_link_libs.profiler import Profiler
import json

Profiler.active = True

_MAX_LEN_PAYLOAD = const(400)
_MAX_LEN_PACKET = const(500)

_CMD_HOST_AVAILABLE = const(1)
_CMD_HOST_STATUS = const(2)


class WlanClient:
    """A class that will control the Wlan of a host board"""

    def __init__(self, commlink: WUart, reset_pin: Pin, ready_pin: Pin, debug: int = 0):
        self._frames = Frames(commlink, _MAX_LEN_PAYLOAD, _MAX_LEN_PACKET, debug=debug)
        self._comm = commlink
        self._debug = debug
        self._preset = reset_pin
        reset_pin.init(mode=Pin.OUT, value=1)
        self._pready = ready_pin
        ready_pin.init(mode=Pin.IN)
        self._host_reset_count = -1  # to keep track of broken sockets so not all reset the host
        # ready_pin.irq(handler=self._host_ready,trigger=Pin.IRQ_RISING, hard=True)

    def _reset_host(self):
        self._host_reset_count += 1
        self._preset(0)  # reset host board, not done due to debugging
        time.sleep_ms(100)
        self._preset(1)
        time.sleep(1)

    def start(self, timeout=10):
        st = time.ticks_ms()
        self._reset_host()
        while time.ticks_diff(time.ticks_ms(), st) < timeout * 1000:
            time.sleep_ms(500)  # host board booting up
            if self.connected():
                print("Resetting host and connecting took {}s".format(
                    time.ticks_diff(time.ticks_ms(), st) / 1000))
                return
        raise OSError("WlanHost not connected")

    def connected(self) -> bool:
        try:
            resp, payload = self._frames.send_cmd_wait_answer(_CMD_HOST_AVAILABLE)
            # resp can only be true, otherwise module is not reachable -> OSError in Communication
        except OSError as e:
            if self._debug >= 1:
                print("Connection issue", e)
            return False
        finally:
            gc.collect()
        return True

    def status(self, key=None):
        """returns multiple information about #sockets, mem_free, wifi status ..."""
        try:
            resp, payload = self._frames.send_cmd_wait_answer(_CMD_HOST_STATUS)
        except OSError as e:
            if self._debug >= 1:
                print("Connection issue", e)
            return False
        finally:
            gc.collect()
        if resp:
            print("Status recv", payload)
            st = json.loads(payload)
            if key:
                return st[key]
            else:
                return st
