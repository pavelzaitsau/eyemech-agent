"""Drive the HTTP surface through fake streams.

The fake writer refuses str the way a MicroPython stream does. That is not
pedantry: the first version of `_respond` handed it a str, which raised inside
the handler and reached the client as a dropped socket.
"""

import asyncio
import json
import unittest

import shim  # noqa: F401

import eyemech
import server


class FakeReader:
    def __init__(self, data):
        self.data = data
        self.position = 0

    async def readline(self):
        end = self.data.find(b"\n", self.position)
        end = len(self.data) if end == -1 else end + 1
        chunk = self.data[self.position:end]
        self.position = end
        return chunk

    async def readexactly(self, count):
        chunk = self.data[self.position:self.position + count]
        self.position += count
        return chunk


class FakeWriter:
    def __init__(self):
        self.out = bytearray()

    def write(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("a stream takes bytes, not %s" % type(data).__name__)
        self.out += data

    async def drain(self):
        pass

    def close(self):
        pass

    async def wait_closed(self):
        pass


def request(method, path, body=None):
    head = "%s %s HTTP/1.1\r\nHost: eye\r\n" % (method, path)
    if body is None:
        return (head + "\r\n").encode()
    payload = json.dumps(body)
    head += "Content-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(payload)
    return (head + payload).encode()


class HttpCase(unittest.TestCase):
    def setUp(self):
        self.eye = eyemech.Eye()
        self.controller = server.Controller(self.eye)
        self.handler = server.make_handler(self.controller)

    def call(self, method, path, body=None):
        writer = FakeWriter()
        asyncio.run(self.handler(FakeReader(request(method, path, body)), writer))
        text = bytes(writer.out).decode()
        head, _, payload = text.partition("\r\n\r\n")
        status = int(head.split(" ")[1])
        return status, json.loads(payload)


class TestRoutes(HttpCase):
    def test_state_reports_the_pose(self):
        status, payload = self.call("GET", "/state")
        self.assertEqual(status, 200)
        self.assertIn("lr_ticks", payload)
        self.assertIn("pwm_lr", payload)
        self.assertIn("mode", payload)

    def test_look_moves_the_eye(self):
        status, payload = self.call("POST", "/look", {"x": -0.5, "y": 0.3})
        self.assertEqual(status, 200)
        self.assertEqual(payload["x"], -0.5)
        self.assertEqual(payload["pwm_lr"], payload["lr_ticks"])

    def test_blink_takes_an_empty_body(self):
        status, payload = self.call("POST", "/blink")
        self.assertEqual(status, 200)
        self.assertTrue(payload["blinked"])

    def test_wink_names_the_eye_that_closed(self):
        status, payload = self.call("POST", "/wink", {"side": "left"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["winked"], "left")

    def test_express_names_the_gesture_it_played(self):
        status, payload = self.call("POST", "/express", {"name": "alert"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["expressed"], "alert")

    def test_squint_persists_into_the_next_request(self):
        self.call("POST", "/squint", {"v": 0.4})
        _, payload = self.call("GET", "/state")
        self.assertEqual(payload["squint"], 0.4)

    def test_idle_starts_off_and_can_be_switched_on(self):
        _, payload = self.call("GET", "/state")
        self.assertFalse(payload["idle_enabled"])
        _, payload = self.call("POST", "/idle", {"enabled": True})
        self.assertTrue(payload["idle_enabled"])
        _, payload = self.call("POST", "/idle", {"enabled": False})
        self.assertFalse(payload["idle_enabled"])


class TestRefusals(HttpCase):
    def test_a_missing_argument_is_a_400(self):
        status, payload = self.call("POST", "/look", {"x": 0.1})
        self.assertEqual(status, 400)
        self.assertIn("y", payload["error"])

    def test_an_unknown_side_is_a_400(self):
        status, payload = self.call("POST", "/wink", {"side": "middle"})
        self.assertEqual(status, 400)

    def test_an_unknown_expression_is_a_400(self):
        status, payload = self.call("POST", "/express", {"name": "smug"})
        self.assertEqual(status, 400)
        self.assertIn("smug", payload["error"])

    def test_an_unknown_path_is_a_404(self):
        status, _ = self.call("GET", "/nope")
        self.assertEqual(status, 404)

    def test_a_malformed_request_line_is_a_400(self):
        writer = FakeWriter()
        asyncio.run(self.handler(FakeReader(b"garbage\r\n\r\n"), writer))
        self.assertIn(b"400", bytes(writer.out))


class TestIdleHandover(unittest.TestCase):
    def test_the_eye_holds_still_until_idle_is_asked_for(self):
        # The default is the whole point: an eye that drifts on its own drains
        # the meaning out of the movement that says a session wants an answer.
        controller = server.Controller(eyemech.Eye())
        self.assertFalse(controller.idle_enabled)
        controller.last_command -= server.IDLE_RESUME_MS * 2
        self.assertFalse(controller.idle_due())

    def test_idle_becomes_due_once_it_is_on_and_the_silence_is_long_enough(self):
        controller = server.Controller(eyemech.Eye())
        controller.idle_enabled = True
        controller.last_command -= server.IDLE_RESUME_MS * 2
        self.assertTrue(controller.idle_due())


if __name__ == "__main__":
    unittest.main()
