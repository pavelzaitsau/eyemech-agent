"""Driver and behaviour for the EyeMech e3.2 mechanism.

The public surface is the Eye class: look, blink, squint, neutral, idle.
Positions arrive as -1.0 to 1.0 on each axis, and calibration.py turns them
into PCA9685 ticks.

Every command writes all six channels in one I2C transaction, so the two
halves of an eye never lag each other by a visible margin.
"""

import time
import random
import asyncio
from machine import Pin, I2C

import calibration as cal

# Lid travel that vertical gaze consumes, as a fraction of each lid's range.
# The upper lid follows the pupil down; the lower lid rises a little when the
# eye looks up. Without this the gaze reads as a pupil sliding behind a fixed
# opening.
TOP_FOLLOW_DOWN = 0.50
BOTTOM_FOLLOW_UP = 0.25

BLINK_FLOOR_MS = 93  # Below this the lids do not reach each other.

# Each expression is a gesture, not a state: it ends where it began, with the
# held squint untouched. A frame is (x, y, extra closure, travel ms, hold ms),
# and the gaze runs -1 to 1 as everywhere else.
EXPRESSIONS = {
    # Wide, still, then two fast blinks. Reads as "I need you".
    "alert": (
        (0.0, 0.15, 0.0, 120, 260),
        (0.0, 0.15, 1.0, 93, 60),
        (0.0, 0.15, 0.0, 93, 90),
        (0.0, 0.15, 1.0, 93, 60),
        (0.0, 0.15, 0.0, 93, 240),
    ),
    # Lids down to a slit, a slow sweep across, a pause. Reads as "are you
    # sure": narrowed eyes and an unhurried look, never a blink.
    "suspicious": (
        (0.0, -0.1, 0.45, 140, 90),
        (-0.55, -0.1, 0.45, 220, 110),
        (0.55, -0.1, 0.45, 260, 130),
        (0.0, -0.1, 0.45, 160, 60),
    ),
    # A glance away and back, with one blink on the return.
    "curious": (
        (-0.5, 0.45, 0.0, 200, 320),
        (-0.5, 0.45, 1.0, 93, 70),
        (-0.5, 0.45, 0.0, 93, 160),
    ),
    # Heavy lids, gaze sagging, one long blink.
    "tired": (
        (0.0, -0.35, 0.55, 500, 300),
        (0.0, -0.55, 1.0, 320, 220),
        (0.0, -0.35, 0.55, 320, 260),
    ),
}


def _clamp(value, low=0.0, high=1.0):
    return low if value < low else high if value > high else value


class Eye:
    def __init__(self, i2c=None):
        self.i2c = i2c or I2C(0, scl=Pin(cal.I2C_SCL_PIN),
                              sda=Pin(cal.I2C_SDA_PIN), freq=cal.I2C_FREQ_HZ)
        self._buf = bytearray(24)
        self._x = 0.0
        self._y = 0.0
        self._squint = 0.0
        # Bumped by every commanded move. Idle behaviour captures it and stops
        # writing when it changes, so a request arriving mid-fixation is not
        # overwritten by the drift the fixation was about to restore.
        self._command_gen = 0
        self.configure()

    def configure(self):
        """Wake the chip and set 50 Hz.

        The PCA9685 comes up from any power cycle at 200 Hz, where every servo
        command lands near 460 us. That is below the MG90S minimum, so nothing
        moves while the I2C bus still acknowledges every write.
        """
        cal.configure(self.i2c)

    # --- position ---------------------------------------------------------

    def _gaze_ticks(self):
        x = _clamp(self._x, -1.0, 1.0)
        y = _clamp(self._y, -1.0, 1.0)
        lr = cal.GAZE_LR_CENTRE + x * cal.GAZE_LR_REACH
        reach = cal.GAZE_UD_REACH_UP if y >= 0 else cal.GAZE_UD_REACH_DOWN
        return lr, cal.GAZE_UD_CENTRE + y * reach

    def _lid_closure(self, blink, wink=None):
        """Return closure 0.0-1.0 for TL, BL, TR, BR.

        A blink overrides the other two inputs rather than adding to them, so
        a blink that starts during a squint still reaches full closure.

        `wink` names the eye that closes; the other one keeps whatever the
        squint and the vertical gaze already asked for.
        """
        y = _clamp(self._y, -1.0, 1.0)
        top = _clamp(self._squint + (TOP_FOLLOW_DOWN * -y if y < 0 else 0.0))
        bottom = _clamp(self._squint + (BOTTOM_FOLLOW_UP * y if y > 0 else 0.0))
        shut = (max(top, blink), max(bottom, blink))
        left = shut if wink != "right" else (top, bottom)
        right = shut if wink != "left" else (top, bottom)
        return (left[0], left[1], right[0], right[1])

    def _write(self, blink=0.0, wink=None):
        lr, ud = self._gaze_ticks()
        closure = self._lid_closure(blink, wink)
        values = [int(lr), int(ud)]
        for i in range(4):
            span = cal.LID_SHUT[i] - cal.LID_OPEN[i]
            values.append(int(cal.LID_OPEN[i] + span * closure[i]))
        for i in range(6):
            self._buf[i * 4 + 2] = values[i] & 0xFF
            self._buf[i * 4 + 3] = values[i] >> 8
        self.i2c.writeto_mem(cal.PCA9685_ADDR, cal.LED0_BASE_REG, self._buf)

    # --- commands ---------------------------------------------------------

    def _touch(self):
        self._command_gen = (self._command_gen + 1) & 0xFFFF
        return self._command_gen

    def look(self, x, y):
        """Point the gaze. -1.0 is left and down, 1.0 is right and up.

        The move is a jump: the servo runs at its own speed, about 135 ms for
        the full horizontal sweep. Use glance() for a slower, visible move.
        """
        self._touch()
        self._x, self._y = x, y
        self._write()

    def glance(self, x, y, ms=200):
        """Move the gaze over `ms`, instead of jumping."""
        x0, y0 = self._x, self._y
        steps = max(1, ms // 16)
        for s in range(1, steps + 1):
            t = s / steps
            self._x = x0 + (x - x0) * t
            self._y = y0 + (y - y0) * t
            self._write()
            time.sleep_ms(16)

    def blink(self, ms=BLINK_FLOOR_MS, hold_ms=cal.BLINK_HOLD_MS):
        """Close and reopen the lids.

        `ms` under 93 leaves the lids short of each other: an MG90S cannot
        cross the upper lid's 200 ticks any faster, so the eye never shuts.
        """
        steps = cal.BLINK_STEPS
        delay = max(1, ms // steps)
        for s in range(steps + 1):
            self._write(s / steps)
            time.sleep_ms(delay)
        time.sleep_ms(hold_ms)
        for s in range(steps + 1):
            self._write(1.0 - s / steps)
            time.sleep_ms(delay)

    def squint(self, amount):
        """Hold the lids partly closed. 0.0 is open, 1.0 is shut."""
        self._touch()
        self._squint = _clamp(amount)
        self._write()

    def neutral(self):
        self._touch()
        self._x = self._y = self._squint = 0.0
        self._write()

    def release(self):
        """Stop driving every channel.

        A servo held against a stop draws its full current and heats its
        gearbox. Releasing costs the held position: the lids drop.
        """
        for channel in range(6):
            cal.release(self.i2c, channel)

    # --- autonomous -------------------------------------------------------

    def idle(self, duration_ms=None, should_stop=None):
        """Saccade, fixate and blink until stopped.

        `should_stop` is called between saccades and ends the loop when it
        returns True, which lets a request interrupt the behaviour without
        waiting out a fixation.
        """
        start = time.ticks_ms()
        next_blink = random.randint(1800, 4200)
        while True:
            if duration_ms is not None:
                if time.ticks_diff(time.ticks_ms(), start) >= duration_ms:
                    return
            if should_stop is not None and should_stop():
                return

            x = random.uniform(-1.0, 1.0)
            y = random.uniform(-1.0, 1.0)
            if random.randint(0, 9) < 7:
                self.look(x, y)
                time.sleep_ms(140)
            else:
                self.glance(x, y, 224)

            self._fixate(random.randint(300, 1500))

            elapsed = time.ticks_diff(time.ticks_ms(), start)
            if elapsed > next_blink:
                self.blink()
                next_blink = elapsed + random.randint(1800, 4200)
            if random.randint(0, 19) == 0:
                self.squint(0.45)
                time.sleep_ms(random.randint(400, 900))
                self.squint(0.0)

    def _fixate(self, ms):
        """Hold a target with the small drift a live eye never loses.

        A servo parked on one value looks frozen. Two ticks is about 10 us of
        pulse, which is too small to see as motion but enough to break that.
        """
        x0, y0 = self._x, self._y
        end = time.ticks_add(time.ticks_ms(), ms)
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            self._x = x0 + random.uniform(-0.02, 0.02)
            self._y = y0 + random.uniform(-0.01, 0.01)
            self._write()
            time.sleep_ms(60)
        self._x, self._y = x0, y0

    # --- asyncio variants -------------------------------------------------
    #
    # The blocking versions above hold the scheduler for as long as they run:
    # a blink is 270 ms, which an HTTP request would spend waiting. These
    # yield between frames instead. Behaviour is otherwise identical.

    async def glance_async(self, x, y, ms=200):
        gen = self._touch()
        x0, y0 = self._x, self._y
        steps = max(1, ms // 16)
        for s in range(1, steps + 1):
            if self._command_gen != gen:
                return
            t = s / steps
            self._x = x0 + (x - x0) * t
            self._y = y0 + (y - y0) * t
            self._write()
            await asyncio.sleep_ms(16)

    async def blink_async(self, ms=BLINK_FLOOR_MS, hold_ms=cal.BLINK_HOLD_MS):
        steps = cal.BLINK_STEPS
        delay = max(1, ms // steps)
        for s in range(steps + 1):
            self._write(s / steps)
            await asyncio.sleep_ms(delay)
        await asyncio.sleep_ms(hold_ms)
        for s in range(steps + 1):
            self._write(1.0 - s / steps)
            await asyncio.sleep_ms(delay)

    async def wink_async(self, side, ms=BLINK_FLOOR_MS, hold_ms=cal.BLINK_HOLD_MS):
        """Close one eye and reopen it. `side` is "left" or "right"."""
        if side not in ("left", "right"):
            raise ValueError("side must be left or right")
        steps = cal.BLINK_STEPS
        delay = max(1, ms // steps)
        for s in range(steps + 1):
            self._write(s / steps, side)
            await asyncio.sleep_ms(delay)
        await asyncio.sleep_ms(hold_ms)
        for s in range(steps + 1):
            self._write(1.0 - s / steps, side)
            await asyncio.sleep_ms(delay)

    async def express_async(self, name):
        """Play a named gesture and return the gaze to where it started.

        A command arriving mid-gesture cuts it short, the same way it cuts
        short a fixation: the newest instruction wins rather than queueing
        behind a second of theatre.
        """
        frames = EXPRESSIONS.get(name)
        if frames is None:
            raise ValueError("unknown expression: %s" % name)

        home = (self._x, self._y)
        gen = self._touch()
        closure = 0.0

        for x, y, target, travel_ms, hold_ms in frames + ((home[0], home[1], 0.0, 200, 0),):
            x0, y0, c0 = self._x, self._y, closure
            steps = max(1, travel_ms // 16)
            for step in range(1, steps + 1):
                if self._command_gen != gen:
                    return
                fraction = step / steps
                self._x = x0 + (x - x0) * fraction
                self._y = y0 + (y - y0) * fraction
                closure = c0 + (target - c0) * fraction
                self._write(closure)
                await asyncio.sleep_ms(16)
            if hold_ms:
                await asyncio.sleep_ms(hold_ms)

    async def idle_async(self, should_stop=None):
        """Run the idle behaviour until `should_stop` returns True.

        The check happens between saccades and inside a fixation, so a request
        interrupts within about 60 ms rather than waiting out a 1.5 s hold.
        """
        next_blink = random.randint(1800, 4200)
        start = time.ticks_ms()
        while True:
            if should_stop is not None and should_stop():
                return
            x = random.uniform(-1.0, 1.0)
            y = random.uniform(-1.0, 1.0)
            if random.randint(0, 9) < 7:
                self.look(x, y)
                await asyncio.sleep_ms(140)
            else:
                await self.glance_async(x, y, 224)

            await self._fixate_async(random.randint(300, 1500), should_stop)

            if should_stop is not None and should_stop():
                return

            # A blink runs 270 ms and a squint up to 900 ms. Checking here
            # keeps the worst-case reaction at one saccade rather than one
            # saccade plus whichever of the two had just started.
            elapsed = time.ticks_diff(time.ticks_ms(), start)
            if elapsed > next_blink:
                await self.blink_async()
                next_blink = elapsed + random.randint(1800, 4200)
            elif random.randint(0, 19) == 0:
                self.squint(0.45)
                await asyncio.sleep_ms(random.randint(400, 900))
                self.squint(0.0)

    async def _fixate_async(self, ms, should_stop=None):
        gen = self._command_gen
        x0, y0 = self._x, self._y
        end = time.ticks_add(time.ticks_ms(), ms)
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            if self._command_gen != gen:
                return
            if should_stop is not None and should_stop():
                break
            self._x = x0 + random.uniform(-0.02, 0.02)
            self._y = y0 + random.uniform(-0.01, 0.01)
            self._write()
            await asyncio.sleep_ms(60)
        if self._command_gen == gen:
            self._x, self._y = x0, y0

    def state(self):
        """Return the current gaze and lid state as plain values.

        `pwm_lr` and `pwm_ud` are read back from the chip rather than computed,
        because everything else here reports intent. A servo with no supply,
        or a channel left in full-off, is indistinguishable from a working one
        until someone reads the register the chip actually holds. 4096 is the
        full-off bit: no pulse is leaving that pin.
        """
        lr, ud = self._gaze_ticks()
        regs = self.i2c.readfrom_mem(cal.PCA9685_ADDR, cal.LED0_BASE_REG, 8)
        return {
            "x": round(self._x, 3),
            "y": round(self._y, 3),
            "squint": round(self._squint, 3),
            "lr_ticks": int(lr),
            "ud_ticks": int(ud),
            "pwm_lr": regs[2] | (regs[3] << 8),
            "pwm_ud": regs[6] | (regs[7] << 8),
        }
