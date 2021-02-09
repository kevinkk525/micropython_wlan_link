# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-07 

__updated__ = "2021-02-07"
__version__ = "0.1"


class CommandHandler:
    def __init__(self, amount_commands=127):
        self._table = [None] * amount_commands

    def register(self, command_id):
        """Wrapper to register a function with command com_id"""
        if self._table[command_id] is not None:
            raise ValueError("Command_id {} already registered".format(command_id))

        def wrapper(f):
            print("Setting", f.__name__, "at", command_id)
            self._table[command_id] = f
            return f

        return wrapper

    def get(self, command_id):
        return self._table[command_id]


wlanHandler = CommandHandler(128)
