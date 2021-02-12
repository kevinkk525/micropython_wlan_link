# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-07 

__updated__ = "2021-02-10"
__version__ = "0.3"

from micropython import const
#from wlan_link_libs.crc import crc16
import errno
import time
from wlan_link_libs.uart import WUart
from .profiler import Profiler
import struct
import micropython


# @Profiler.measure
@micropython.native
def hash(header, params=()):
    result = 0xceed

    for msg in ([header], params):
        for arg in msg:
            for c in arg:
                result = (result * 17 ^ c) & 0xffff
    return result


_EXCEPTIONS = (ValueError, TypeError, AttributeError, NotImplementedError, Exception)

_LEN_HEADER = 7
_START_CMD = const(0xE0)
# _END_CMD = const(0xEE) # no need for _END_CMD
_REPLY_FLAG = const(1 << 7)

# RESPONSE FLAGS (3 bits) # Every answer needs a response flag. Commands don't have one.
_RESP_TRUE = const(1)
_RESP_FALSE = const(0)
_RESP_OSERROR = const(2)
_RESP_EXCEPTION = const(3)


# Packet structure (payload is sum of params)
# START_CMD
# header structure: [CMD,#Params|len_packet->2bytes,RESP_CODE,PAYLOAD,CRC (2Byte)] -> 7 byte
# Param header structure: [len_param_0(7bit + 3bit data type), len_param_1, ...] -> #Params bytes
# Param frame: [param1,param2,...] -> sum(params header)

class Frames:
    def __init__(self, commlink: WUart, len_send_buf, len_read_buf, debug=0):
        self._sendbuf = bytearray(len_send_buf)
        self._readbuf = bytearray(len_read_buf)
        self._comm = commlink
        self._debug = debug

    # @Profiler.measure
    def _read_header(self):
        buf = memoryview(self._readbuf)
        cmd = buf[0]
        num_params = (buf[1] & 0x3C) >> 2  # 4bit -> 15 params
        len_packet = (buf[1] & 0x03) << 8 | buf[2]  # 10 bit -> 1023
        # --> buf[1] bit 0&1 free
        response_code = buf[3] >> 4  # 4 bit --> 15
        crc = buf[5] << 8 | buf[6]  # crc16
        payload = buf[4]
        return cmd, num_params, len_packet, response_code, payload, crc

    # @Profiler.measure
    def _check_frame(self):
        _, _, len_packet, _, _, crc = self._read_header()
        buf = memoryview(self._readbuf)
        buf[5] = 0  # reset crc16 in buffer
        buf[6] = 0
        crc_new = hash(buf[:len_packet])
        buf[5] = crc >> 8  # save old crc16 again
        buf[6] = crc & 0xFF
        if crc_new != crc:
            if self._debug >= 1:
                print("CRC wrong, expected", crc, "got", crc_new)
            raise ValueError("CRC wrong, expected {!s} got {!s}".format(crc, crc_new))

    # @Profiler.measure
    def _set_crc(self, num_params, params):
        """
        Calculate crc of given args (e.g. multiple memoryviews for sending).
        Sets the crc in _sendbuf and returns it.
        """
        buf = memoryview(self._sendbuf)
        buf[5] = 0
        buf[6] = 0
        crc = hash(buf[:_LEN_HEADER + num_params * 2], params)
        buf[5] = crc >> 8
        buf[6] = crc & 0xFF

    @staticmethod
    def check_param(param, maxv):
        if param is not None:
            if param > maxv:
                raise ValueError("param can't be >{!s}".format(maxv))

    # @Profiler.measure
    def _create_header(self, cmd, num_params, len_packet, response_code=None, payload=None,
                       is_answer=False):
        if response_code is None:
            response_code = 0x00
        if payload is None:
            payload = 0x00
        if self._debug >= 3:
            print("header", cmd, num_params, response_code, payload, is_answer)
        self.check_param(cmd, 255)
        self.check_param(num_params, 15)
        self.check_param(len_packet, 1023)
        self.check_param(response_code, 15)
        self.check_param(payload, 255)
        buf = memoryview(self._sendbuf)
        if is_answer:
            buf[0] = cmd | _REPLY_FLAG  # reply to cmd
        else:
            buf[0] = cmd
        buf[1] = ((num_params << 2) & 0x3C) | ((len_packet >> 8) & 0x03)
        buf[2] = len_packet & 0xFF
        buf[3] = buf[3] & ((response_code << 4) | 0x0F)
        buf[4] = payload

    # @Profiler.measure
    def _create_param_header(self, params: list, types: list) -> int:
        """Create a param header if more than 1 params in frame, otherwise it is not needed"""
        if len(params) == 0:
            return 0
        sendbuf = memoryview(self._sendbuf)
        for i, param in enumerate(params):
            sendbuf[_LEN_HEADER + i * 2] = (types[i] << 2) & 0x1C | (
                    (len(param) >> 8) & 0x03)
            # 2 bit for length, 3 bit for data type, 3 bit empty
            sendbuf[_LEN_HEADER + i * 2 + 1] = len(param) & 0xFF
        return len(params) * 2

    # @Profiler.measure
    def _transform_from_payload(self, head: memoryview, p: memoryview):
        cnt = 0
        params = []
        for i in range(0, len(head), 2):
            # 2 byte in param_header for type and param length
            l = ((head[i] & 0x03) << 8) | (head[i + 1] & 0xFF)
            t = (head[i] & 0x1C) >> 2
            param = p[cnt:cnt + l]
            cnt += l
            try:
                params.append(self._transform_from_bytearray(param, t))
            except Exception as e:
                if self._debug > 0:
                    print("Error transforming param from bytearray:", e)
                params.append(param)  # just leaving it as bytearray
        return params

    @staticmethod
    def _transform_from_bytearray(param, t):
        if t == 0:  # bytearray, might become a string or other usage. Application has to decide
            return param
        elif t == 1:  # int, stored as hex in bytearray
            return struct.unpack("i", param)[0]
        elif t == 2:  # float
            return struct.unpack("f", param)[1]
        elif t == 3:  # None
            return None
        elif t == 4:  # bool
            return True if param[0] == 0x01 else False
        else:
            raise TypeError("Unknown type number {}".format(t))

    @staticmethod
    def _transform_to_bytearray(param):
        if type(param) in (bytearray, memoryview, bytes):
            return param, 0
        elif type(param) == int:
            return struct.pack("i", param), 1
        elif type(param) == float:
            return struct.pack("f", param), 2
        elif type(param) == str:
            return param.encode(), 0
        elif param is None:
            return b'\x00', 3
        elif type(param) == bool:
            return (b'\x01', 4) if param is True else (b'\x00', 4)
        else:
            raise TypeError("Type {} can't be sent".format(type(param)))

    # @Profiler.measure
    def _read_packet(self):
        # TODO: handle timeouts from uart
        readbuf = memoryview(self._readbuf)
        self._comm.read_frame(readbuf, _LEN_HEADER)
        # will time out after 10ms which indicates an error
        cmd, num_params, len_packet, response_code, payload, crc = self._read_header()
        if self._debug >= 3:
            print("Got header:", cmd, num_params, len_packet, response_code, payload, crc)
        if num_params > 0:
            self._comm.read_frame(readbuf[_LEN_HEADER:], len_packet - _LEN_HEADER)
        self._check_frame()
        if num_params == 0:
            payload = [payload]  # response_code in header. might be 0x00 = None
        else:
            param_header = readbuf[_LEN_HEADER:_LEN_HEADER + num_params * 2]
            payloadb = readbuf[_LEN_HEADER + num_params * 2:len_packet]
            payload = self._transform_from_payload(param_header, payloadb)
        if self._debug >= 3:
            print("Got params")
            for param in payload:
                if type(param) != memoryview:
                    print(param)
                else:
                    print(bytes(param))

        # Note: Callbacks will receive all params as memoryview objects and can convert them with
        # bytes(param) if they need to. This reduces RAM usage and relocations.
        return cmd, num_params, len_packet, response_code, payload

    async def await_and_read_message(self):
        await self._comm.await_byte(_START_CMD)
        try:
            cmd, num_params, len_packet, response_code, payload = self._read_packet()
        except Exception as e:
            if self._debug >= 1:
                print("Frame broken, discarding. Connection good?", e)
                import sys
                sys.print_exception(e)
            raise OSError(errno.ETIMEDOUT)
        if self._debug >= 2:
            print("Received full frame:", cmd, num_params, len_packet, response_code, payload)
        return cmd, response_code, payload

    # @Profiler.measure
    def wait_and_read_message(self, timeout=1000):
        """wait for a new message until timeout in ms is reached"""
        if not self._comm.wait_byte(_START_CMD, True, timeout=timeout):
            raise OSError(errno.ETIMEDOUT)
        # TODO: all uart can time out if packet breaks and will return None. No function can handle this yet!!
        try:
            cmd, num_params, len_packet, response_code, payload = self._read_packet()
        except Exception as e:
            if self._debug >= 1:
                print("Frame broken, discarding. Connection good?", e)
                import sys
                sys.print_exception(e)
            raise OSError(errno.ETIMEDOUT)
        if self._debug >= 2:
            print("Received full frame:", cmd, num_params, len_packet, response_code, payload)
        return cmd, response_code, payload

    # @Profiler.measure
    def _create_packet(self, cmd, num_params, response_code, *args, is_answer=False) -> list:
        # num_params can be 0 with response_code and payload in header but
        # also >=1 with payload in params
        if self._debug >= 3:
            print("cp", cmd, num_params, response_code, args, is_answer)
        len_packet = _LEN_HEADER
        params = []
        if num_params > 0:
            types = []
            for param in args:
                param, t = self._transform_to_bytearray(param)
                len_packet += len(param)
                params.append(param)
                types.append(t)
            len_packet += self._create_param_header(params, types)
        self._create_header(cmd, num_params, len_packet, response_code,
                            args[0] if num_params == 0 and len(args) > 0 else None,  # resp_payload
                            is_answer=is_answer)
        self._set_crc(num_params, params)
        return params if num_params > 0 else []

    # @Profiler.measure
    def _write_packet(self, num_params, *args):
        stu = time.ticks_us()
        self._comm.write_byte(_START_CMD)
        sendbuf = memoryview(self._sendbuf)
        self._comm.write(sendbuf[:_LEN_HEADER + num_params * 2])
        for m in args:
            self._comm.write(m)
        if self._debug >= 3:
            print("writing took", time.ticks_us() - stu)

    def create_packet(self, cmd, response_code: int = None, *args, is_answer=False) -> list:
        if len(args) == 1 and type(args[0]) == int and args[0] < 256:
            num_params = 0
        else:
            num_params = len(args)
        params = self._create_packet(cmd, num_params, response_code, *args, is_answer=is_answer)
        return params

    def _is_answer(self, cmd, cmdr):
        if cmd | _REPLY_FLAG != cmdr:
            if self._debug >= 1:
                print("not respone", cmd, cmdr)
            raise ValueError("not response")  # TODO: different error type?

    @Profiler.measure
    def send_cmd_wait_answer(self, cmd, params: list or tuple = (), timeout=1000) -> (
            int, list or tuple):
        if type(params) not in (list, tuple):
            params = (params,)
        self.create_and_send_packet(cmd, params=params, is_answer=False)
        cmdr, response_coder, paramsr = self.wait_and_read_message(timeout)
        if self._debug >= 3:
            print("scwa", cmdr, response_coder, paramsr)
        self._is_answer(cmd, cmdr)
        return self.translate_answer(response_coder, paramsr)

    def create_and_send_packet(self, cmd, response_code: int = None, params: list or tuple = (),
                               is_answer=False):
        if type(params) not in (list, tuple):
            params = [params]
        if self._debug >= 3:
            print("casp", cmd, response_code, params)
        params = self.create_packet(cmd, response_code, *params, is_answer=is_answer)
        self._write_packet(len(params), *params)

    @staticmethod
    def _find_exception(exc):
        if isinstance(exc, Exception):  # exception got raised and will be sent back
            t = type(exc)
            if t in _EXCEPTIONS:
                return _EXCEPTIONS.index(t)
            raise TypeError("Exception type {} not supported".format(t))
        elif type(exc) == int:  # received exception from host
            return _EXCEPTIONS[exc]
        else:
            print("Exception not understood", exc)

    def translate_answer(self, response_code, params=None):
        if response_code == _RESP_FALSE or response_code == _RESP_TRUE:
            if params:
                if type(params) in (list, tuple) and len(params) == 1:
                    return params[0]
                else:
                    return params
            return True if response_code == _RESP_TRUE else False
        elif response_code == _RESP_OSERROR:
            raise OSError(params[0])
        elif response_code == _RESP_EXCEPTION:
            exc = self._find_exception(int(bytes(params[0])))
            raise exc(bytes(params[1]).decode(), True, "Exc from host")
            # e.args[2]=True to be able to distinguish
            # between host exceptions and client exceptions during function call
        else:
            raise ValueError("unknown scenario", response_code, params)

    def send_true(self, cmd, response_payload=None):
        self.create_and_send_packet(cmd, _RESP_TRUE, response_payload, is_answer=True)

    def send_false(self, cmd, response_payload=None):
        self.create_and_send_packet(cmd, _RESP_FALSE, response_payload, is_answer=True)

    def send_oserror(self, cmd, error_number=None):
        self.create_and_send_packet(cmd, _RESP_OSERROR, error_number, is_answer=True)

    def send_exception(self, cmd, exception):
        exc_type = self._find_exception(exception)
        self.create_and_send_packet(cmd, _RESP_EXCEPTION, (exc_type, exception.args[0]),
                                    is_answer=True)
