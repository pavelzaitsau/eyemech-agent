"""Let the firmware import and run under CPython.

The board's modules reach for `machine`, `network` and the MicroPython-only
halves of `time` and `asyncio`. This installs stand-ins for all four, so the
tests need neither a board nor a servo.

The fake I2C is not a stub that swallows writes: it keeps a register file and
hands it back on read, which is how a test can assert the ticks that reached
the chip. Import this module before anything from `firmware/`.
"""

import asyncio
import os
import sys
import time
import types

FIRMWARE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware")


class Pin:
    IN = 0
    OUT = 1
    PULL_UP = 2
    PULL_DOWN = 3

    def __init__(self, id, mode=None, pull=None):
        self.id = id
        self.mode = mode

    def value(self, level=None):
        return 0


class I2C:
    """A PCA9685 as far as the firmware can tell: 256 addressable registers."""

    def __init__(self, *args, **kwargs):
        self.registers = bytearray(256)
        self.writes = 0

    def scan(self):
        return [0x40]

    def writeto_mem(self, address, register, buffer):
        self.writes += 1
        self.registers[register:register + len(buffer)] = buffer

    def readfrom_mem(self, address, register, length):
        return bytes(self.registers[register:register + length])


class WLAN:
    STA_IF = 0

    def __init__(self, interface):
        self._connected = True

    def active(self, on=None):
        return True

    def isconnected(self):
        return self._connected

    def connect(self, ssid, password):
        self._connected = True

    def disconnect(self):
        self._connected = False

    def ifconfig(self, config=None):
        return ("192.168.1.210", "255.255.255.0", "192.168.1.1", "192.168.1.1")


def _install():
    machine = types.ModuleType("machine")
    machine.Pin = Pin
    machine.I2C = I2C
    sys.modules["machine"] = machine

    network = types.ModuleType("network")
    network.WLAN = WLAN
    network.STA_IF = 0
    sys.modules["network"] = network

    # MicroPython's tick helpers, and the sleeps the firmware awaits. Sleeping
    # for real would make a blink test take a third of a second for nothing.
    time.ticks_ms = lambda: int(time.monotonic() * 1000)
    time.ticks_diff = lambda a, b: a - b
    time.ticks_add = lambda a, b: a + b
    time.sleep_ms = lambda ms: None

    async def sleep_ms(ms):
        await asyncio.sleep(0)

    asyncio.sleep_ms = sleep_ms

    if FIRMWARE not in sys.path:
        sys.path.insert(0, FIRMWARE)


_install()
