# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-11 

__updated__ = "2021-02-11"
__version__ = "0.1"

import network

st = network.WLAN(network.STA_IF)
st.active(True)
st.connect("SSID", "PW")

import machine
from wlan_link_libs.uart import WUart
from wlan_client.wclient import WlanClient

from machine import Pin

uart = machine.UART(1, tx=17, rx=16, baudrate=460800)  # 115200)
wuart = WUart(uart, debug=0)
wl = WlanClient(wuart, Pin(19), Pin(21), debug=1)

from wlan_link_libs.profiler import Profiler

Profiler.active = False

from wlan_client import socket as rsocket

# Now use rsocket to connect e.g. to an echo server running on your PC.
