# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-10 

__updated__ = "2021-02-10"
__version__ = "0.1"

# Module based on usocket

from micropython import const
from .wclient import get_client, WlanClient
import errno
from wlan_link_libs.profiler import Profiler

SOCK_STREAM = const(1)
AF_INET = const(2)

_MAX_LEN_PAYLOAD = const(400)

_CMD_GETADDRINFO = const(20)
_CMD_GET_SOCKET = const(21)
_CMD_CLOSE_SOCKET = const(22)
_CMD_CONNECT_SOCKET = const(23)
_CMD_SEND_SOCKET = const(24)
_CMD_RECV_SOCKET = const(25)

_SOCKET_TCP_MODE = const(1)


def getaddrinfo(host: str, port: int, family=0, socktype=0, proto=0, flags=0):
    """Given a hostname and a port name, return a 'socket.getaddrinfo'
    compatible list of tuples. Honestly, we ignore anything but host & port"""
    if not isinstance(port, int):
        raise TypeError("Port must be an integer")
    ipaddr = get_client().send_cmd_wait_answer(_CMD_GETADDRINFO, (host, port))
    print("getaddr", ipaddr)
    ipaddr = WlanClient.transform_args(ipaddr, str)
    return [(AF_INET, socktype, proto, "", (ipaddr, port))]


# TODO: handle connection exceptions
# TODO: implement timeout with blocking socket

class socket:
    def __init__(self, family=AF_INET, type=SOCK_STREAM, proto=0,
                 fileno=None, socknum=None):
        if family != AF_INET:
            raise TypeError("Only AF_INET family supported")
        if type != SOCK_STREAM:
            raise TypeError("Only SOCK_STREAM type supported")
        self._buffer = b""
        self._socknum = socknum if socknum else get_client().send_cmd_wait_answer(_CMD_GET_SOCKET)
        self._timeout = None  # None=blocking without timeout, 0=non-blocking
        self._blocking = True
        self._closed = False
        print(self._socknum)

    def _check_closed(self):
        if self._closed:
            raise OSError(errno.EBADF)

    def close(self):
        if not self._closed:
            get_client().send_cmd_wait_answer(_CMD_CLOSE_SOCKET, self._socknum)
            self._closed = True

    def setblocking(self, blocking: bool):
        self._blocking = blocking

    def connect(self, address, conntype=None):
        """Connect the socket to the 'address' (which can be 32bit packed IP or
        a hostname string). 'conntype' is an extra that may indicate SSL or not,
        depending on the underlying interface"""
        self._check_closed()
        host, port = address
        if conntype is None:
            conntype = _SOCKET_TCP_MODE
        try:
            get_client().send_cmd_wait_answer(_CMD_CONNECT_SOCKET,
                                              (
                                                  self._socknum, host, port, conntype,
                                                  self._blocking),
                                              timeout=30000 if self._blocking else 1000)
        except Exception as e:
            self.close()
            raise e
        self._buffer = b""

    @Profiler.measure
    def send(self, data) -> int:
        """Send some data to the socket"""
        self._check_closed()
        if len(data) > _MAX_LEN_PAYLOAD:
            raise ValueError("Payload too long")  # could split it up but good for now.
        if len(data) > 1023:  # limited to 255 because of 10 bit for param length in param header
            d = [self._socknum]
            c = 0
            if type(data) != memoryview:
                data = memoryview(data)
            while c < len(data):
                d.append(data[c:c + 1023])
                c += 1023
        else:
            d = (self._socknum, data)
        return get_client().send_cmd_wait_answer(_CMD_SEND_SOCKET, d)

    @Profiler.measure
    def recv(self, bufsize=0):
        self._check_closed()
        if bufsize == 0:
            return b''
        elif bufsize > _MAX_LEN_PAYLOAD:
            bufsize = _MAX_LEN_PAYLOAD  # let application handle shorter reads.
        d = get_client().send_cmd_wait_answer(_CMD_RECV_SOCKET,
                                              (self._socknum, bufsize, self._blocking),
                                              timeout=None if self._blocking else 1000)
        return bytes(d)  # can't return memoryview as this is the client's buffer

    def __del__(self):
        """Just in case?"""
        print("__del__")
        if not self._closed:
            self.close()
