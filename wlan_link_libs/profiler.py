# Author: Kevin Köck
# Copyright Kevin Köck 2021 Released under the MIT license
# Created on 2021-02-08 

__updated__ = "2021-02-09"
__version__ = "0.2"

# Profiler class for debugging. Decorate functions to measure their execution time.

# TODO: support Async functions.

import time
import gc


class Profiler:
    _storage = []
    active = True

    @staticmethod
    def measure(f):
        if not Profiler.active:
            return f

        def wrapper(*args, **kwargs):
            m = gc.mem_free()
            n = f.__name__ if hasattr(f, "__name__") else str(f)
            stu = time.ticks_us()
            Profiler._storage.append((stu, m, n, -1))
            try:
                r = f(*args, **kwargs)
            finally:
                etu = time.ticks_us()
                Profiler._storage.append((stu, m, n, time.ticks_diff(etu, stu)))
            return r

        return wrapper

    @staticmethod
    def reset():
        Profiler._storage = []

    @staticmethod
    def print():
        print("State Depth Starttime Mem_free  ExecTi \tFunction name")
        depth = -1

        def depth_t(d):
            return (" " * d + str(d) + " " * (4 - d)) if d < 5 else " " * 3 + str(d)

        for func in Profiler._storage:
            if func[3] == -1:
                state = "  -->"
                depth += 1
                depth_f = depth_t(depth)
            else:
                state = "<--  "
                depth_f = depth_t(depth)
                depth -= 1
            print("{} {} {} {}Byt  {}{}\t{}".format(state, depth_f, func[0], func[1],
                                                    func[3] if func[3] > 0 else "   ",
                                                    "us" if func[3] > 0 else "  ",
                                                    func[2]))
