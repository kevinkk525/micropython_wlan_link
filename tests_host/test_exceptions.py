# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-10 

__updated__ = "2021-02-10"
__version__ = "0.1"

from wlan_host.command_handler import wlanHandler
from wlan_host.whost import WlanHost


@wlanHandler.register(126)
def raiseOS(wl: WlanHost, *args):
    try:
        import errno
        raise OSError(errno.EAGAIN)
    except OSError as e:
        print("raising OSError", e.args[0])
        return OSError, e.args[0]


@wlanHandler.register(127)
def raiseEx(wl: WlanHost, *args):
    try:
        raise TypeError("Typing..")
    except Exception as e:
        print("raising Exception", e, e.args[0])
        return e
