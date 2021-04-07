# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-03-14 

__updated__ = "2021-03-14"
__version__ = "0.1"

from wlan_link_libs.ringbuf import Ringbuf

r = Ringbuf(15)
print(r._free())
m = b"0123456789"
print(r.append(m))
print(r.append(m))
print(r._buf)
print(r.get(5))
print(r.append(m))
print(r._buf)
print(r.append(m))
print(r.get())
