# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-03-14 

__updated__ = "2021-03-15"
__version__ = "0.3"

import time


class Ringbuf:
    def __init__(self, length):
        self._buf = bytearray(length + 1)  # keeping 1 free so pointers don't clash when full
        self._p_read = 0  # buf read until here
        self._p_add = 0  # point to the end of the buf
        self._length = length + 1

    def append(self, mem):
        if len(mem) > self._free() - 1:  # keeping 1 byte free
            return False
        a, b = self._free_slices_mmview()
        if len(mem) > len(a):
            a[:] = mem[:len(a)]
            r = len(mem) - len(a)
            b[:r] = mem[-r:]
        else:
            a[:len(mem)] = mem
        self._p_add += len(mem)
        if self._p_add > self._length:
            self._p_add -= self._length
        return True

    def get(self, amount=-1, blocking=False, timeout=None):
        return self._get(amount, blocking, timeout=timeout, mmview=False)

    def get_mmview(self, amount=-1, blocking=False, timeout=None):
        return self._get(amount, blocking, timeout=timeout, mmview=True)

    def advance_read(self, amount):
        self._p_read += amount
        if self._p_read > self._length:
            self._p_read -= self._length
        # TODO: activate after having tested ringbuffer
        # if self._p_read == self._p_add:  # buffer empty
        #    self._p_read = self._p_add = 0 # resetting to 0 for performance reasons.

    def wait_available(self, amount, sleep_ms=1, timeout=None):
        st = time.ticks_ms()
        while self._length - self._free() < amount:
            time.sleep_ms(sleep_ms)
            if timeout and time.ticks_diff(time.ticks_ms(), st) > timeout:
                return False
        return True

    def any(self):
        return self._length - self._free()

    def _get(self, amount=-1, blocking=False, timeout=None, mmview=False):
        """
        Returns given amount of bytes from Ringbuf.
        :param amount: Amount to read
        :param blocking: if true, waits until enough data is available. if false, returns as much as possible
        :param mmview: returns memoryview of the data. Will not advance the pointer!
        :return: bytes or memoryview
        """
        if amount == -1:
            amount = self._length - 1
        if blocking and not self.wait_available(amount, timeout=timeout):
            return False
        a, b = self._full_slices_mmview()
        if amount <= len(a):
            if not mmview:
                self.advance_read(amount)
            return bytes(a[:amount]) if not mmview else (a[:amount], a[0:0])
        else:
            if not mmview:
                self.advance_read(amount)
                ret = bytes(a)
                if len(b) >= amount - len(a):
                    ret += bytes(b[:amount - len(a)])
                else:
                    ret += bytes(b)  # short read
                return ret
            else:
                return a, b[:amount - len(a)] if len(b) >= amount - len(a) else b

    def _free(self):
        if self._p_add >= self._p_read:
            return self._length + self._p_read - self._p_add
        else:
            return self._p_read - self._p_add

    def _free_slices(self):
        if self._p_add >= self._p_read:
            return self._length - self._p_read, self._p_add
        else:
            return self._p_read - self._p_add

    def _free_slices_mmview(self):
        mv = memoryview(self._buf)
        if self._p_add >= self._p_read:
            return mv[self._p_add:], mv[:self._p_read]
        else:
            return mv[self._p_add:self._p_read], mv[0:0]

    def _full_slices_mmview(self):
        mv = memoryview(self._buf)
        if self._p_add >= self._p_read:
            return mv[self._p_read:self._p_add], mv[0:0]
        else:
            return mv[self._p_read:], mv[:self._p_add]
