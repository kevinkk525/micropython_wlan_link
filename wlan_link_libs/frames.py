# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-07 

__updated__ = "2021-02-09"
__version__ = "0.2"

from micropython import const
from wlan_link_libs.crc import crc8
import errno
import time
from wlan_link_libs.uart import WUart
from .profiler import Profiler

_EXCEPTIONS = (ValueError, TypeError, AttributeError, NotImplementedError, Exception)

_LEN_HEADER = 4
_START_CMD = const(0xE0)
_END_CMD = const(0xEE)
# _ERR_CMD = const(0xEF)
_REPLY_FLAG = const(1 << 7)
# _CMD_FLAG = const(0)

# RESPONSE FLAGS (3 bits)
# RESP = 0 not used, it means None
_RESP_TRUE = const(2)
_RESP_FALSE = const(1)
_RESP_OSERROR = const(3)
_RESP_EXCEPTION = const(4)


# TODO: BUG: With num_params>1 each param can only be 255 bytes long because each param gets only
#  1 byte in param_header for its length. With 1 param only it can be 1023 bytes.

# Packet structure (payload is sum of params)
# START_CMD
# header structure: [CMD,#Params|len_packet->2bytes,CRC] -> 4 bytes
# Param header structure: [len_param_0, len_param_1, ...] -> #Params bytes
# Param frame: [param1,param2,...] -> sum(params header)
# END_CMD


class Frames:
    def __init__(self, commlink: WUart, len_send_buf, len_read_buf, debug=0):
        self._sendbuf = bytearray(len_send_buf)
        self._readbuf = bytearray(len_read_buf)
        self._comm = commlink
        self._debug = debug

    # @Profiler.measure
    def _check_frame(self):
        _, _, len_packet, _, _, crc, _ = self._read_header()
        buf = memoryview(self._readbuf)
        buf[3] = 0  # reset crc in buffer
        crc_new = crc8(buf[:len_packet])
        buf[3] = crc
        if crc_new != crc:
            if self._debug >= 1:
                print("CRC wrong, expected", crc, "got", crc_new)
            raise ValueError("CRC wrong, expected {!s} got {!s}".format(crc, crc_new))

    # @Profiler.measure
    def _read_header(self):
        buf = memoryview(self._readbuf)
        cmd = buf[0]
        if buf[1] >> 7 != 0x01:  # params
            num_params = (buf[1] & 0x1C) >> 2
            len_packet = (buf[1] & 0x03) << 8 | buf[2]
            response_code = None
            payload = None
            response_in_params = (buf[1] & 0x20) >> 5
        else:  # no params
            len_packet = _LEN_HEADER
            payload = (buf[1] & 0x03) << 8 | buf[2]
            response_code = (buf[1] & 0x1C) >> 2
            if response_code == 0x00 and payload == 0x00:
                response_code = None
                payload = None
            response_in_params = 0
            num_params = 0
        crc = buf[3]
        return cmd, num_params, len_packet, response_code, payload, crc, response_in_params

    # @Profiler.measure
    def _set_crc(self, num_params, *args):
        """
        Calculate crc of given args (e.g. multiple memoryviews for sending).
        Sets the crc in _sendbuf and returns it.
        """
        buf = memoryview(self._sendbuf)
        buf[3] = 0
        len_param_header = 0 if num_params <= 1 else num_params
        if num_params == 0:
            crc = crc8(buf[:_LEN_HEADER + len_param_header])
        else:
            crc = crc8(buf[:_LEN_HEADER + len_param_header], *args)
        buf[3] = crc

    # @Profiler.measure
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
        # print("header", cmd, num_params, response_code, payload, is_answer)
        self.check_param(cmd, 255)
        self.check_param(num_params, 7)
        self.check_param(len_packet, 1023)
        self.check_param(response_code, 7)
        self.check_param(payload, 1023)
        buf = memoryview(self._sendbuf)
        if is_answer:
            buf[0] = cmd | _REPLY_FLAG  # reply to cmd
        else:
            buf[0] = cmd
        if response_code > 0:
            resp_flag = 1
        else:
            resp_flag = 0
        if num_params > 0:
            # 3 bits num_params, 10 bits len_packet, bit1=reply flag, bit3=response_code in params flag
            buf[1] = ((num_params << 2) & 0x1C) | ((resp_flag << 5) & 0x20) | (
                    (len_packet >> 8) & 0x03)
            buf[2] = len_packet & 0xFF
        else:
            # 3 bits answer code, 10 bits payload, bit #1 in buf[1] is flag for response_code
            buf[1] = (0x01 << 7) | ((response_code << 2) & 0x1C) | ((payload >> 8) & 0x03)
            buf[2] = payload & 0xFF
        # leaves 3 bits available in sendbuf[1]

    # @Profiler.measure
    def _create_param_header(self, num_params: int, payload: list or tuple):
        """Create a param header if more than 1 params in frame, otherwise it is not needed"""
        if num_params <= 1:
            return 0
        for i in range(num_params):
            self._sendbuf[_LEN_HEADER + i] = len(payload[i])
        return num_params

    # @Profiler.measure
    def _read_packet(self):
        # TODO: handle timeouts from uart
        readbuf = memoryview(self._readbuf)
        self._comm.read_frame(readbuf, _LEN_HEADER)
        # will time out after 10ms which indicates an error
        cmd, num_params, len_packet, response_code, payload, crc, resp_param = self._read_header()
        if self._debug >= 2:
            print("Got header:", cmd, num_params, len_packet, response_code, payload, crc)
        payload = [payload]
        cnt = _LEN_HEADER
        if num_params > 1:
            self._comm.read_frame(memoryview(readbuf)[cnt:], num_params)
            param_header = memoryview(readbuf)[cnt:cnt + num_params]
            cnt += num_params
        elif num_params == 1:
            param_header = bytearray(1)
            param_header[0] = len_packet - _LEN_HEADER
        else:
            param_header = None
        if num_params > 0:
            payloadb = memoryview(readbuf)[cnt:len_packet]
            self._comm.read_frame(payloadb, len(payloadb))
            payload = []
        pc = 0
        for num in range(num_params):
            payload.append(payloadb[pc:pc + param_header[num]])
            pc += param_header[num]
        if self._debug >= 2:
            print("Got params")
            for param in payload:
                if param is not None:
                    print(bytes(param))
        if resp_param:
            response_code = payload[0]
            payload.pop(0)
        # Note: Callbacks will receive all params as memoryview objects and can convert them with
        # bytes(param) if they need to. This reduces RAM usage and relocations.
        return cmd, num_params, len_packet, response_code, payload

    async def _await_and_read_message(self):
        await self._comm.await_byte(_START_CMD)
        cmd, num_params, len_packet, response_code, payload = self._read_packet()
        if not await self._comm.await_byte(_END_CMD, wait=False):
            if self._debug >= 1:
                print("Frame broken, discarding. Connection good?")
            raise OSError(errno.ETIMEDOUT)
        self._check_frame()
        if self._debug >= 3:
            print("Received full frame:", cmd, num_params, len_packet, response_code, payload)
        return cmd, num_params, len_packet, response_code, payload

    async def await_and_read_message(self):
        cmd, num_params, len_packet, response_code, params = await self._await_and_read_message()
        return cmd, response_code, params

    def wait_and_read_message(self):
        cmd, num_params, len_packet, response_code, params = self._wait_and_read_message()
        return cmd, response_code, params

    @Profiler.measure
    def _wait_and_read_message(self, timeout=1000):
        """wait for a new message until timeout in ms is reached"""
        if not self._comm.wait_byte(_START_CMD, True, timeout=timeout):
            raise OSError(errno.ETIMEDOUT)
        # TODO: all uart can time out if packet breaks and will return None. No function can handle this yet!!
        cmd, num_params, len_packet, response_code, payload = self._read_packet()
        if not self._comm.wait_byte(_END_CMD, False, timeout=2):  # 2ms timeout, data should exist
            if self._debug >= 1:
                print("Frame broken, discarding. Connection good?")
            raise OSError(errno.ETIMEDOUT)
        self._check_frame()
        if self._debug >= 3:
            print("Received full frame:", cmd, num_params, len_packet, response_code, payload)
        return cmd, num_params, len_packet, response_code, payload

    @Profiler.measure
    def _create_packet(self, cmd, num_params, *args, response_code=None, is_answer=False):
        # num_params can be 0 with response_code and payload in header but
        # also >1 with payload in params
        len_packet = _LEN_HEADER + self._create_param_header(num_params, args)
        if num_params > 0:
            for param in args:
                len_packet += len(param)
        self._create_header(cmd, num_params, len_packet, response_code,
                            args[0] if num_params == 0 and len(args) > 0 else None,
                            is_answer=is_answer)
        self._set_crc(num_params, *args)

    @Profiler.measure
    def _write_packet(self, num_params, *args):
        stu = time.ticks_us()
        self._comm.write_byte(_START_CMD)
        sendbuf = memoryview(self._sendbuf)
        num_params_header = 0 if num_params <= 1 else num_params
        # no param header needed for 1 param since length is obvious
        self._comm.write(sendbuf[:_LEN_HEADER + num_params_header])
        for m in args:
            self._comm.write(m)
        self._comm.write_byte(_END_CMD)
        if self._debug >= 3:
            print("writing took", time.ticks_us() - stu)

    def create_packet(self, cmd, response_code: int = None, response_payload=None,
                      params: list or tuple = (),
                      is_answer=False):
        # if there is a response_code, response and payload are in header, otherwise as params.
        if response_code is not None and response_payload is not None:
            self._create_packet(cmd, 0, response_payload, response_code=response_code,
                                is_answer=is_answer)
        elif response_code is not None:
            # response code but payload too big for header
            self._create_packet(cmd, len(params), *params, response_code=response_code,
                                is_answer=is_answer)
        else:
            self._create_packet(cmd, len(params), *params, is_answer=is_answer)

    def _is_answer(self, cmd, cmdr):
        if cmd | _REPLY_FLAG != cmdr:
            if self._debug >= 1:
                print("not respone", cmd, cmdr)
            raise ValueError("not response")  # TODO: different error type?

    @Profiler.measure
    def send_cmd_wait_answer(self, cmd, params: list or tuple = ()) -> (int, list or tuple):
        self.create_and_send_packet(cmd, params=params, is_answer=False)
        cmdr, response_coder, paramsr = self.wait_and_read_message()
        if self._debug >= 3:
            print("scwa", cmdr, response_coder, paramsr)
        self._is_answer(cmd, cmdr)
        return self.translate_answer(response_coder, paramsr)

    def create_and_send_packet(self, cmd, response_code: int = None, response_payload=None,
                               params: list or tuple = (),
                               is_answer=False):
        if self._debug >= 3:
            print("casp", cmd, response_code, response_payload, params)
        if type(response_payload) == tuple:
            if len(response_payload) == 1:
                response_payload = response_payload[0]
        if response_code is not None and response_payload is not None and (
                type(response_payload) != int or response_payload > 1023):
            # response payload too big for header, send both as params
            if response_payload is None:
                response_payload = 0x00
            if type(response_payload) in (list, tuple):
                params = [bytearray(1)] + list(response_payload)
            else:
                params = (bytearray(1), response_payload)
            params[0][0] = response_code
            response_payload = None
        params = list(params)
        for i, param in enumerate(params):
            if type(param) in (int, float):
                params[i] = str(param).encode()
            elif type(param) == str:
                params[i] = param.encode()
            elif type(param) not in (bytearray, bytes):
                raise TypeError("param {} is not byte object".format(param))
        print("created", cmd, response_code, response_payload, params)
        self.create_packet(cmd, response_code, response_payload, params, is_answer)
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

    def translate_answer(self, response_code=None, params=None):
        if type(response_code) in (bytearray, memoryview):
            response_code = response_code[0]
        if response_code == _RESP_TRUE:
            return [True] + params
        elif response_code == _RESP_FALSE:
            return [False] + params
        elif response_code == _RESP_OSERROR:
            raise OSError(params[0])
        elif response_code == _RESP_EXCEPTION:
            exc = self._find_exception(int(bytes(params[0])))
            raise exc(bytes(params[1]).decode(), True)  # e.args[2]=True to be able to distinguish
            # between host exceptions and client exceptions during function call
        else:
            raise ValueError("unknown scenario", response_code, params)

    def send_true(self, cmd, response_payload=None):
        self.create_and_send_packet(cmd, _RESP_TRUE, response_payload, is_answer=True)

    def send_false(self, cmd, response_payload=None):
        self.create_and_send_packet(cmd, _RESP_FALSE, response_payload, is_answer=True)

    def send_answer(self, cmd, params: list or tuple):
        self.create_and_send_packet(cmd, params=params, is_answer=True)

    def send_oserror(self, cmd, error_number=None):
        self.create_and_send_packet(cmd, _RESP_OSERROR, error_number, is_answer=True)

    def send_exception(self, cmd, exception):
        exc_type = self._find_exception(exception)
        self.create_and_send_packet(cmd, _RESP_EXCEPTION, (exc_type, exception.args[0]),
                                    is_answer=True)
