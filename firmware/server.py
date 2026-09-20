"""HTTP control surface for the eye.

    POST /look    {"x": -1.0..1.0, "y": -1.0..1.0}
    POST /blink   {"ms": 93}                      (body optional)
    POST /squint  {"v": 0.0..1.0}
    POST /wink    {"side": "left"|"right", "ms": 93}
    POST /express {"name": "alert"|"suspicious"|"curious"|"tired"}
    POST /idle    {"enabled": true|false}
    GET  /state

Idle behaviour runs as a background task. Every request pushes the idle task
out of the way; it returns once IDLE_RESUME_MS passes with no further request,
so a caller that stops talking does not leave the eye frozen mid-saccade.

The server binds to the local network with no authentication, which Pavel chose
on 2026-09-20: the eye sits on a home network. Moving it anywhere shared means
adding a check here first, because anyone who can reach the port can drive it.
"""

import asyncio
import json
import time

import wifi

IDLE_RESUME_MS = 8000
MAX_BODY_BYTES = 512


class Controller:
    def __init__(self, eye):
        self.eye = eye
        self.last_command = time.ticks_ms()
        self.driven = False
        # Off by default: the eye holds still unless something is waiting on an
        # answer, and drifting on its own drains that signal of meaning. POST
        # /idle with true turns the autonomous movement back on for a session.
        self.idle_enabled = False
        self.idle_error = None

    def touch(self):
        self.last_command = time.ticks_ms()

    def idle_due(self):
        if not self.idle_enabled:
            return False
        return time.ticks_diff(time.ticks_ms(), self.last_command) > IDLE_RESUME_MS


async def behaviour(ctl):
    """Alternate between idle behaviour and holding the commanded pose.

    An exception used to end this task outright, and asyncio swallows the
    traceback. The eye then went still for good while /state still reported
    "idle", which reads as working. Catching it here keeps the loop alive and
    puts the reason in /state, where it can be seen without a serial cable.
    """
    while True:
        if ctl.idle_due():
            ctl.driven = False
            try:
                await ctl.eye.idle_async(should_stop=lambda: not ctl.idle_due())
            except Exception as exc:
                ctl.idle_error = repr(exc)
                print("idle behaviour failed:", ctl.idle_error)
                await asyncio.sleep_ms(500)
        else:
            ctl.driven = True
            await asyncio.sleep_ms(100)


def _float(payload, key, default=None):
    value = payload.get(key, default)
    if value is None:
        raise ValueError("missing %s" % key)
    return float(value)


async def _read_request(reader):
    """Return (method, path, payload) or raise ValueError on a malformed head."""
    line = await reader.readline()
    if not line:
        raise ValueError("empty request")
    parts = line.split()
    if len(parts) < 2:
        raise ValueError("bad request line")
    method, path = parts[0].decode(), parts[1].decode()

    length = 0
    while True:
        header = await reader.readline()
        if not header or header == b"\r\n":
            break
        name, _, value = header.decode().partition(":")
        if name.strip().lower() == "content-length":
            length = min(int(value.strip()), MAX_BODY_BYTES)

    payload = {}
    if length:
        body = await reader.readexactly(length)
        if body.strip():
            payload = json.loads(body)
    return method, path, payload


async def _respond(writer, status, payload):
    # Encode here: a MicroPython stream takes bytes, and handing it a str
    # raises inside the handler, where the client sees only a dropped socket.
    body = json.dumps(payload).encode()
    head = (
        "HTTP/1.1 %s\r\nContent-Type: application/json\r\n"
        "Content-Length: %d\r\nConnection: close\r\n\r\n" % (status, len(body))
    ).encode()
    writer.write(head + body)
    await writer.drain()


def make_handler(ctl):
    async def handle(reader, writer):
        try:
            method, path, payload = await _read_request(reader)
        except Exception as exc:
            await _respond(writer, "400 Bad Request", {"error": str(exc)})
            writer.close()
            return

        try:
            if method == "GET" and path == "/state":
                state = ctl.eye.state()
                state["mode"] = "driven" if ctl.driven else "idle"
                state["idle_enabled"] = ctl.idle_enabled
                state["wifi_reconnects"] = wifi.reconnects
                if ctl.idle_error:
                    state["idle_error"] = ctl.idle_error
                await _respond(writer, "200 OK", state)

            elif method == "POST" and path == "/look":
                ctl.touch()
                ctl.eye.look(_float(payload, "x"), _float(payload, "y"))
                await _respond(writer, "200 OK", ctl.eye.state())

            elif method == "POST" and path == "/blink":
                ctl.touch()
                await ctl.eye.blink_async(int(payload.get("ms", 93)))
                await _respond(writer, "200 OK", {"blinked": True})

            elif method == "POST" and path == "/wink":
                ctl.touch()
                side = payload.get("side")
                await ctl.eye.wink_async(side, int(payload.get("ms", 93)))
                await _respond(writer, "200 OK", {"winked": side})

            elif method == "POST" and path == "/express":
                ctl.touch()
                name = payload.get("name")
                await ctl.eye.express_async(name)
                await _respond(writer, "200 OK", {"expressed": name})

            elif method == "POST" and path == "/idle":
                ctl.idle_enabled = bool(payload.get("enabled", True))
                if not ctl.idle_enabled:
                    ctl.touch()
                await _respond(writer, "200 OK", {"idle_enabled": ctl.idle_enabled})

            elif method == "POST" and path == "/squint":
                ctl.touch()
                ctl.eye.squint(_float(payload, "v"))
                await _respond(writer, "200 OK", ctl.eye.state())

            else:
                await _respond(writer, "404 Not Found", {"error": path})

        except ValueError as exc:
            await _respond(writer, "400 Bad Request", {"error": str(exc)})
        except Exception as exc:
            await _respond(writer, "500 Internal Server Error", {"error": str(exc)})

        writer.close()
        await writer.wait_closed()

    return handle


async def serve(eye, port=80):
    """Run the server and the idle task until cancelled."""
    ctl = Controller(eye)
    asyncio.create_task(behaviour(ctl))
    server = await asyncio.start_server(make_handler(ctl), "0.0.0.0", port)
    return ctl, server
