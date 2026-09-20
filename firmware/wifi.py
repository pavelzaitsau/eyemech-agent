"""Join the network named in secrets.py, at a fixed address.

secrets.py stays off the board's repository and out of every log. It holds two
names:

    SSID = "your-network"
    PASSWORD = "your-password"

Without that file the eye still runs; main.py falls back to idle behaviour
alone and never starts the server.
"""

import asyncio
import network
import time

# A fixed address, because the MCP server is configured with one URL and a new
# DHCP lease would break every tool call with no visible cause. 210 sits well
# above the addresses this network has handed out (the highest seen was 62), so
# the router is unlikely to lease it to something else while the eye is off.
STATIC_CONFIG = ("192.168.1.210", "255.255.255.0", "192.168.1.1", "192.168.1.1")


def connect(timeout_ms=20000, static=STATIC_CONFIG):
    """Associate and return the assigned address.

    Pass `static=None` to take whatever DHCP offers instead.

    Raises OSError when the association does not complete in time, which
    usually means a wrong password rather than a missing access point: a
    wrong SSID fails immediately, a wrong password retries until the timeout.
    """
    import secrets

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if static:
        # Must precede connect(). Applied afterwards, the DHCP client has
        # already replaced it.
        wlan.ifconfig(static)
    if not wlan.isconnected():
        wlan.connect(secrets.SSID, secrets.PASSWORD)
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while not wlan.isconnected():
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                wlan.disconnect()
                raise OSError("wifi: no association within %d ms" % timeout_ms)
            time.sleep_ms(200)
    return wlan.ifconfig()[0]


reconnects = 0


async def supervise(period_ms=5000):
    """Re-associate after the link drops.

    A dropped association does not close the listening socket, so the server
    goes on serving a network nobody can reach it from. From outside, the board
    is simply gone, which is the failure a health check reports as a timeout.
    """
    global reconnects
    while True:
        await asyncio.sleep_ms(period_ms)
        if network.WLAN(network.STA_IF).isconnected():
            continue
        try:
            here = connect()
        except OSError as exc:
            print("wifi: reconnect failed:", exc)
            continue
        reconnects += 1
        print("wifi: reconnected at", here)


def address():
    """Return the current address, or None when the board is not associated."""
    wlan = network.WLAN(network.STA_IF)
    return wlan.ifconfig()[0] if wlan.isconnected() else None
