# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-06 

__updated__ = "2021-02-10"
__version__ = "0.3"

import gc
from micropython import const
import uasyncio as asyncio
from wlan_link_libs.frames import Frames
from wlan_link_libs.uart import WUart
import time
from machine import Pin
from wlan_link_libs.profiler import Profiler
from .command_handler import wlanHandler
import json
import network

Profiler.active = False

_wlan_host = None

_MAX_LEN_PAYLOAD = const(400)
_MAX_LEN_PACKET = const(500)

_CMD_HOST_AVAILABLE = const(1)
_CMD_HOST_STATUS = const(2)
_CMD_HOST_START = const(3)


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
        self._started = False  # TODO: don't execute other functions if not started?
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
                if resp is None:
                    raise TypeError("No registered function is allowed to return None")
                elif type(resp) not in (list, tuple):
                    resp = (resp,)
                if resp[0] is True:
                    self._frames.send_true(cmd, resp[1:] if len(resp) > 1 else None)
                elif resp[0] is False:
                    self._frames.send_false(cmd, resp[1:] if len(resp) > 1 else None)
                elif resp[0] == OSError:
                    self._frames.send_oserror(cmd, resp[1])
                elif type(resp[0]) == OSError:
                    self._frames.send_oserror(cmd, resp[0].args[0])
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
            if self._debug>=1:
                print("Time to answer sent", time.ticks_diff(etu, stu))
                print("Whost got packet", cmd, response_code, params)
                try:
                    for param in params:
                        if type(param) in (bytearray, memoryview):
                            print(bytes(param))
                        else:
                            print(param)
                except:
                    pass
            gc.collect()

    @wlanHandler.register(_CMD_HOST_AVAILABLE)
    def available(self, wl, *args):
        """Just a simple ping-like response to proof that the host is reachable"""
        return True

    @wlanHandler.register(_CMD_HOST_STATUS)
    def status(self, *args):
        """Return statistics about host, #sockets, mem_free, wifi status etc"""
        st = dict()
        st["num_sockets"] = 0  # TODO: when sockets implemented
        st["mem_free"] = gc.mem_free()
        st["wlan_connected"] = network.WLAN(network.STA_IF).isconnected()
        return True, json.dumps(st).encode()

    @staticmethod
    def transform_args(param: memoryview, param_type: int | float | str | bytearray | bytes):
        return Frames.transform_args(param, param_type)

    @wlanHandler.register(_CMD_HOST_START)
    def start(self, ftp_active, max_sockets, socket_buf_len, max_payload_len, debug):
        ftp_active = self.transform_args(ftp_active, bool)
        max_sockets = self.transform_args(max_sockets, int)
        socket_buf_len = self.transform_args(socket_buf_len, int)
        max_payload_len = self.transform_args(max_payload_len, int)
        debug = self.transform_args(debug, int)
        from .socket import Sockets
        Sockets.max_sockets = max_sockets
        Sockets.socket_rx_buffer = socket_buf_len  # TODO: does not impact Frames buffer length yet!
        Sockets.max_payload_len = max_payload_len  # So don't make this bigger than the Frames buf
        self._debug = debug
        self._frames._debug = debug
        # Sockets reads debug from wlhost
        if ftp_active:
            import ftp_thread
        return True


def get_host() -> WlanHost:
    return _wlan_host
