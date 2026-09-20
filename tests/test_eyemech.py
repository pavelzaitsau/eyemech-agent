"""Check what the driver writes to the chip, not what it intends."""

import asyncio
import unittest

import shim  # noqa: F401

import calibration as cal
import eyemech


def ticks(eye, channel):
    """Read one channel's off-count back out of the fake register file."""
    base = cal.LED0_BASE_REG + 4 * channel
    registers = eye.i2c.readfrom_mem(cal.PCA9685_ADDR, base, 4)
    return registers[2] | (registers[3] << 8)


CH_LR, CH_UD, CH_TL, CH_BL, CH_TR, CH_BR = range(6)


class TestGaze(unittest.TestCase):
    def setUp(self):
        self.eye = eyemech.Eye()

    def test_centre_writes_the_measured_centre(self):
        self.eye.look(0, 0)
        self.assertEqual(ticks(self.eye, CH_LR), cal.GAZE_LR_CENTRE)
        self.assertEqual(ticks(self.eye, CH_UD), cal.GAZE_UD_CENTRE)

    def test_the_extremes_reach_the_measured_reach(self):
        self.eye.look(-1, 0)
        self.assertEqual(ticks(self.eye, CH_LR), cal.GAZE_LR_CENTRE - cal.GAZE_LR_REACH)
        self.eye.look(1, 0)
        self.assertEqual(ticks(self.eye, CH_LR), cal.GAZE_LR_CENTRE + cal.GAZE_LR_REACH)

    def test_a_command_beyond_the_range_is_clamped(self):
        self.eye.look(-5, 5)
        self.assertEqual(ticks(self.eye, CH_LR), cal.GAZE_LR_CENTRE - cal.GAZE_LR_REACH)
        self.assertEqual(ticks(self.eye, CH_UD), cal.GAZE_UD_CENTRE + cal.GAZE_UD_REACH_UP)

    def test_state_reports_the_registers_and_not_the_intent(self):
        self.eye.look(-0.5, 0.25)
        state = self.eye.state()
        self.assertEqual(state["pwm_lr"], ticks(self.eye, CH_LR))
        self.assertEqual(state["pwm_ud"], ticks(self.eye, CH_UD))


class TestLids(unittest.TestCase):
    def setUp(self):
        self.eye = eyemech.Eye()

    def test_looking_down_draws_the_upper_lids_after_the_pupil(self):
        self.eye.look(0, 0)
        level = ticks(self.eye, CH_TL)
        self.eye.look(0, -1)
        self.assertNotEqual(ticks(self.eye, CH_TL), level)

    def test_a_squint_moves_every_lid(self):
        self.eye.neutral()
        open_lids = [ticks(self.eye, c) for c in (CH_TL, CH_BL, CH_TR, CH_BR)]
        self.eye.squint(0.5)
        for channel, was in zip((CH_TL, CH_BL, CH_TR, CH_BR), open_lids):
            self.assertNotEqual(ticks(self.eye, channel), was)

    def test_a_blink_closes_both_eyes_fully(self):
        self.eye.neutral()
        asyncio.run(self.eye.blink_async())
        # The blink ends open again, so assert against the midpoint of the run.
        self.eye._write(1.0)
        for index, channel in enumerate((CH_TL, CH_BL, CH_TR, CH_BR)):
            self.assertEqual(ticks(self.eye, channel), cal.LID_SHUT[index])

    def test_a_wink_closes_one_eye_and_leaves_the_other(self):
        self.eye.neutral()
        open_lids = [ticks(self.eye, c) for c in (CH_TL, CH_BL, CH_TR, CH_BR)]
        self.eye._write(1.0, "right")
        self.assertEqual(ticks(self.eye, CH_TL), open_lids[0])
        self.assertEqual(ticks(self.eye, CH_BL), open_lids[1])
        self.assertEqual(ticks(self.eye, CH_TR), cal.LID_SHUT[2])
        self.assertEqual(ticks(self.eye, CH_BR), cal.LID_SHUT[3])

    def test_a_blink_reaches_full_closure_over_a_held_squint(self):
        self.eye.squint(0.4)
        self.eye._write(1.0)
        for index, channel in enumerate((CH_TL, CH_BL, CH_TR, CH_BR)):
            self.assertEqual(ticks(self.eye, channel), cal.LID_SHUT[index])


class TestExpressions(unittest.TestCase):
    def setUp(self):
        self.eye = eyemech.Eye()

    def test_every_expression_returns_the_gaze_it_borrowed(self):
        for name in eyemech.EXPRESSIONS:
            self.eye.look(0.3, -0.2)
            asyncio.run(self.eye.express_async(name))
            state = self.eye.state()
            self.assertAlmostEqual(state["x"], 0.3, places=2, msg=name)
            self.assertAlmostEqual(state["y"], -0.2, places=2, msg=name)

    def test_a_held_squint_survives_a_gesture(self):
        self.eye.squint(0.4)
        asyncio.run(self.eye.express_async("curious"))
        self.assertEqual(self.eye.state()["squint"], 0.4)

    def test_an_unknown_name_is_refused(self):
        with self.assertRaises(ValueError):
            asyncio.run(self.eye.express_async("smug"))

    def test_a_command_cuts_a_gesture_short(self):
        self.eye.look(0.0, 0.0)

        async def scenario():
            task = asyncio.create_task(self.eye.express_async("suspicious"))
            await asyncio.sleep(0)
            self.eye.look(-1.0, 0.0)
            await task

        asyncio.run(scenario())
        self.assertEqual(self.eye.state()["x"], -1.0)


class TestIdleHandover(unittest.TestCase):
    def test_a_command_stops_the_fixation_overwriting_it(self):
        # The fixation used to restore the position it captured on entry, which
        # threw away a command that arrived while it was running.
        eye = eyemech.Eye()
        eye.look(0.5, 0.5)

        async def scenario():
            task = asyncio.create_task(eye._fixate_async(500))
            await asyncio.sleep(0)
            eye.look(-1.0, 0.0)
            await task

        asyncio.run(scenario())
        self.assertEqual(eye.state()["x"], -1.0)
        self.assertEqual(ticks(eye, CH_LR), cal.GAZE_LR_CENTRE - cal.GAZE_LR_REACH)


if __name__ == "__main__":
    unittest.main()
