from .profiler import Profiler
import micropython
import array
import gc

POLYNOMIAL = 0xA001


def _initial(c):
    crc = 0
    for j in range(8):
        if (crc ^ c) & 0x1:
            crc = (crc >> 1) ^ POLYNOMIAL
        else:
            crc = crc >> 1
        c = c >> 1
    return crc


crc16_tab = array.array("H", [_initial(i) for i in range(256)])
gc.collect()


@Profiler.measure
@micropython.native
def crc16(header, params=(), initial_value=0):
    _tab = crc16_tab
    crc = initial_value
    for msg in ([header], params):
        for arg in msg:
            for c in arg:
                crc = (crc >> 8) ^ _tab[(crc ^ c) & 0xff]
    return crc
