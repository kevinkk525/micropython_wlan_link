# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-07 

__updated__ = "2021-02-09"
__version__ = "0.2"

import machine
import uasyncio as asyncio
import time
from .profiler import Profiler


# from wlan_link_libs.frames import _LEN_HEADER


class CommError(OSError):
    pass


class WUart:
    def __init__(self, uart: machine.UART, debug: int = 0):
        self._uart = uart
        self._uart.init(timeout=10)
        self._ustream = asyncio.StreamReader(uart)
        self._debug = debug

    def get_ready(self):
        self._flush_uart()

    async def await_byte(self, b, wait=True):
        stu = time.ticks_us()
        if self._debug >= 3:
            print("Awaiting", b)
        while True:
            data = await self._ustream.read(1)
            if self._debug >= 3:
                print("Read byte", data[0])
            if data[0] == b:
                if self._debug >= 3:
                    print("Found", data, "waited", time.ticks_diff(time.ticks_us(), stu))
                return True
            elif not wait:
                if self._debug >= 1:
                    print("Read", data, "Expected", b)
                return False

    @Profiler.measure
    def wait_byte(self, b, wait=True, timeout=None):
        st = time.ticks_ms()
        stu = time.ticks_us()
        if self._debug >= 3:
            print("Waiting for", b, "t", timeout)
        while True:
            if self._uart.any():
                data = self._uart.read(1)
                if self._debug >= 3:
                    print("Read byte", data[0])
            else:
                if timeout and time.ticks_diff(time.ticks_ms(), st) > timeout:
                    return False
                time.sleep_ms(1)
                continue
            if data[0] == b:
                # if self._debug >= 3:
                etu = time.ticks_us()
                print("Found", data, "waited", time.ticks_diff(etu, stu))
                return True
            elif not wait:
                if self._debug >= 1:
                    print("Read", data, "Expected", b)
                return False

    def _flush_uart(self):
        while self._uart.any():
            self._uart.read(self._uart.any())

    # @Profiler.measure
    def _uart_write(self, buf):
        l = self._uart.write(buf)
        if l is None:
            if self._debug >= 1:
                print("Timeout writing to UART")
            raise CommError("Timeout writing to UART")
        elif l != len(buf):
            if self._debug >= 1:
                print("Short write on UART")
            raise CommError("Short write on UART")

    # @Profiler.measure
    def write(self, buf):
        self._uart.write(buf)

    # @Profiler.measure
    def write_byte(self, b):
        if type(b) not in (bytearray, bytes):
            c = bytearray(1)
            c[0] = b
            self._uart_write(c)
        else:
            self._uart_write(b)

    # @Profiler.measure
    def read_frame(self, buffer, length, timeout=10):
        to_read = length
        st = time.ticks_ms()
        stu = time.ticks_us()
        while to_read and time.ticks_diff(time.ticks_ms(), st) < timeout:
            if self._uart.any():
                r = self._uart.readinto(buffer, to_read)  # does RPI PICO support timeout yet?
                if r is None:
                    if self._debug >= 1:
                        print("No more data on uart, expected", length, "got", r, "bytes")
                    raise CommError("Short read on uart")
                to_read -= r
            else:
                time.sleep_us(100)
        if to_read:
            if self._debug >= 1:
                print("Timeout reading frame")
            raise CommError("Short read on uart with timeout")
        if self._debug >= 3:
            etu = time.ticks_us()
            print("reading frame took", time.ticks_diff(etu, stu))
