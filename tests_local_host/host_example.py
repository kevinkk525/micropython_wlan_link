# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-11 

__updated__ = "2021-02-11"
__version__ = "0.1"

import network

st = network.WLAN(network.STA_IF)
st.active(True)
st.connect("SSID", "PW")

import uasyncio as asyncio
from machine import Pin

from wlan_host.whost import WlanHost
from wlan_link_libs.uart import WUart

import machine

DEBUG = 3

uart = machine.UART(1, tx=17, rx=16, baudrate=460800)  # 115200)
wuart = WUart(uart, debug=DEBUG)

wl = WlanHost(wuart, Pin(33), debug=DEBUG)

import wlan_host.socket

loop = asyncio.get_event_loop()
loop.run_forever()

# You may configure a webrepl to see what's going on or connect to the UART.
# Library doesn't yet support controlling the host wifi from the client so you need to set
# the SSID and PW in this file for now.
