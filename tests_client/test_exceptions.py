# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-10 

__updated__ = "2021-02-10"
__version__ = "0.1"

from wlan_client.wclient import get_client


def raiseOS():
    resp, payload = get_client().send_cmd_wait_answer(126)


def raiseEx():
    resp = get_client().send_cmd_wait_answer(127)
    print("ex", resp)
