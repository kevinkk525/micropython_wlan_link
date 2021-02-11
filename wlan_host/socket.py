# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-10 

__updated__ = "2021-02-10"
__version__ = "0.1"

from micropython import const
from .whost import get_host
from .command_handler import wlanHandler
from wlan_host.whost import WlanHost
import usocket
import gc
import errno
import sys

_MAX_LEN_PAYLOAD = const(400)

_CMD_GETADDRINFO = const(20)
_CMD_GET_SOCKET = const(21)
_CMD_CLOSE_SOCKET = const(22)
_CMD_CONNECT_SOCKET = const(23)
_CMD_SEND_SOCKET = const(24)
_CMD_RECV_SOCKET = const(25)

_SOCKET_TCP_MODE = const(1)


@wlanHandler.register(_CMD_GETADDRINFO)
def getaddrinfo(wl: WlanHost, host: str, port: int, family=0, socktype=0, proto=0, flags=0):
    host = bytes(host).decode()
    port = int(bytes(port))
    # print("getaddrinfo", host, port, family, socktype, proto, flags)
    try:
        return True, usocket.getaddrinfo(host, port, family, socktype, proto, flags)[0][4][0]
    except Exception as e:
        if wl._debug >= 1:
            sys.print_exception(e)
        return e


def socknum_gen():
    pid = 0
    while True:
        pid = pid + 1 if pid < 65535 else 1
        yield pid


class Sockets:
    _sockets = {}
    _newpid = socknum_gen()
    max_sockets = 16  # ESP32 raises Exception with more than 5 sockets?
    active_sockets = 0
    socket_rx_buffer = 400  # rx buffer for socket object

    @staticmethod
    @wlanHandler.register(_CMD_GET_SOCKET)
    def create_socket(wl: WlanHost, *args):
        if Sockets.active_sockets >= Sockets.max_sockets:
            if wl._debug >= 1:
                print("Maximum configured sockets reached")
            return OSError(23)
        try:
            s = usocket.socket()
        except Exception as e:
            if wl._debug >= 1:
                sys.print_exception(e)
            return e
        pid = next(Sockets._newpid)
        while pid in Sockets._sockets:
            pid = next(Sockets._newpid)
        Sockets._sockets[pid] = socket(s, pid, Sockets.socket_rx_buffer)
        return True, pid

    @staticmethod
    def _get_socket(socknum):
        if socknum in Sockets._sockets:
            return Sockets._sockets[socknum]
        else:
            raise TypeError("Socket {} does not exist".format(socknum))

    @staticmethod
    def _remove_socket(socknum):
        del Sockets._sockets[socknum]

    @staticmethod
    @wlanHandler.register(_CMD_CONNECT_SOCKET)
    def connect(wl: WlanHost, socknum, host, port, conntype, blocking):
        socknum = wl.transform_args(socknum, int)
        host = wl.transform_args(host, str)
        port = wl.transform_args(port, int)
        conntype = wl.transform_args(conntype, int)
        blocking = wl.transform_args(blocking, bool)
        if wl._debug >= 3:
            print("connect", socknum, host, port, conntype, blocking)
        try:
            sock = Sockets._get_socket(socknum)
        except OSError as e:
            return e
        return sock.connect(host, port, conntype, blocking)

    @staticmethod
    @wlanHandler.register(_CMD_CLOSE_SOCKET)
    def close(wl: WlanHost, socknum):
        socknum = wl.transform_args(socknum, int)
        try:
            sock = Sockets._get_socket(socknum)
        except OSError as e:
            if e.args[0] == errno.EBADF:  # socket already removed
                return True
            return e
        sock.close()
        Sockets._remove_socket(socknum)
        del sock
        gc.collect()
        if wl._debug >= 3:
            print("Closed socket", socknum)
        return True

    @staticmethod
    @wlanHandler.register(_CMD_SEND_SOCKET)
    def send(wl: WlanHost, socknum, *args):
        socknum = wl.transform_args(socknum, int)
        try:
            sock = Sockets._get_socket(socknum)
        except OSError as e:
            return e
        return sock.send(*args)

    @staticmethod
    @wlanHandler.register(_CMD_RECV_SOCKET)
    def recv(wl: WlanHost, socknum, bufsize, blocking):
        socknum = wl.transform_args(socknum, int)
        bufsize = wl.transform_args(bufsize, int)
        blocking = wl.transform_args(blocking, bool)
        try:
            sock = Sockets._get_socket(socknum)
        except TypeError:
            if wl._debug >= 3:
                print("Socket doesn't exist", socknum)
            return OSError, errno.EBADF
        return sock.recv(bufsize, blocking)


class socket:
    def __init__(self, sock: usocket, socknum: int, len_buffer: int):
        self._socknum = socknum
        self._sock = sock
        self._buffer = bytearray(len_buffer)
        self._conntype = None

    def connect(self, host: str, port: int, conntype: int, blocking: bool):
        print("Connecting")
        self._conntype = conntype
        self._sock.setblocking(blocking)
        try:
            self._sock.connect((host, port))
            print("Connected")
            return True
        except OSError as e:
            return e
        finally:
            if blocking:
                self._sock.setblocking(False)  # internally we'll use non-blocking sockets

    def close(self):
        self._sock.close()
        return True

    def send(self, *args):
        cnt = 0
        for arg in args:
            try:
                cnt += self._sock.send(arg)
            except Exception as e:
                return e
        return True, cnt

    def recv(self, bufsize, blocking):
        # for now blocking=True will freeze the esp32 which is not desirable.
        self._sock.setblocking(blocking)
        try:
            data = self._sock.recv(bufsize)
        except Exception as e:
            sys.print_exception(e)
            return e
        if len(data) > 255:  # limited to 255 because of 1 byte for param length in param header
            d = [True]
            c = 0
            if type(data) != memoryview:
                data = memoryview(data)
            while c < len(data):
                d.append(data[c:c + 255])
                c += 255
            return d
        return True, data
