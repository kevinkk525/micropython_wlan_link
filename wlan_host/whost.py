# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-06 

__updated__ = "2021-02-09"
__version__ = "0.2"

import gc
from micropython import const
import uasyncio as asyncio
from wlan_link_libs.frames import Frames
from wlan_link_libs.uart import WUart
import time
from machine import Pin
from wlan_link_libs.profiler import Profiler
from .CommandHandler import wlanHandler
import json
import network

Profiler.active = False

_wlan_host = None


def get_host():
    return _wlan_host


_MAX_LEN_PAYLOAD = const(400)
_MAX_LEN_PACKET = const(500)

_CMD_HOST_AVAILABLE = const(1)
_CMD_HOST_STATUS = const(2)


class WlanHost:
    """A class that will control a micropython board to provide WLAN to other micropython boards"""

    def __init__(self, commlink: WUart, ready_pin: Pin, debug: int = 0):
        self._frames = Frames(commlink, _MAX_LEN_PAYLOAD, _MAX_LEN_PACKET, debug=debug)
        self._comm = commlink
        self._debug = debug
        self._pready = ready_pin
        ready_pin.init(mode=Pin.OUT, value=0)
        global _wlan_host
        _wlan_host = self
        self._listen_task = asyncio.create_task(self.listen())
        # notify client on restart by signalling data available.

    async def listen(self):
        gc.collect()
        self._comm.get_ready()  # flushing uart
        if self._debug >= 3:
            print("ready to listen")
        gc.collect()
        while True:
            print("start while")
            try:
                cmd, response_code, params = await self._frames.await_and_read_message()
            except OSError:
                if self._debug >= 1:
                    print("Error reading frame")
                continue
            except Exception as e:
                if self._debug >= 1:
                    import sys
                    sys.print_exception(e)
                continue
            print("got frame", cmd, response_code, params)
            stu = time.ticks_us()
            try:
                resp = wlanHandler.get(cmd)(self, *params)
                if type(resp) not in (list, tuple):
                    resp = (resp,)
                if resp[0] is True:
                    self._frames.send_true(cmd, resp[1:] if len(resp) > 1 else None)
                elif resp[0] is False:
                    self._frames.send_false(cmd, resp[1:] if len(resp) > 1 else None)
                elif resp[0] == OSError:
                    self._frames.send_oserror(cmd, resp[1])
                elif isinstance(resp[0], Exception):
                    self._frames.send_exception(cmd, resp[0])
                else:
                    print("Unknown format", resp[0], resp)
            except Exception as e:
                if self._debug >= 1:
                    import sys
                    sys.print_exception(e)
                continue
            etu = time.ticks_us()
            print("Time to write", time.ticks_diff(etu, stu))
            print("Whost got packet", cmd, response_code, params)
            for param in params:
                if type(param) == bytearray:
                    print(bytes(param))
                else:
                    print(param)
            gc.collect()

    @wlanHandler.register(_CMD_HOST_AVAILABLE)
    def available(self, wl, *args):
        """Just a simple ping-like response to proof that the host is reachable"""
        return True

    @wlanHandler.register(_CMD_HOST_STATUS)
    def status(self, wl, *args):
        """Return statistics about host, #sockets, mem_free, wifi status etc"""
        st = dict()
        st["num_sockets"] = 0  # TODO: when sockets implemented
        st["mem_free"] = gc.mem_free()
        st["wlan_connected"] = network.WLAN(network.STA_IF).isconnected()
        return True, json.dumps(st).encode()
