"""Guard the measured numbers.

These values were read off one physical mechanism over two evenings, and a
typo in them is a servo pressing into a printed part. Nothing here proves the
eye is calibrated; it proves the table is internally consistent and inside the
servo's window.
"""

import unittest

import shim  # noqa: F401  (installs the fake machine before the import below)

import calibration as cal

LIDS = ("TL", "BL", "TR", "BR")


class TestPulseWindow(unittest.TestCase):
    def test_every_position_is_inside_the_mg90s_window(self):
        positions = list(cal.LID_SHUT) + list(cal.LID_OPEN) + [
            cal.GAZE_LR_LEFT, cal.GAZE_LR_CENTRE, cal.GAZE_LR_RIGHT,
            cal.GAZE_UD_DOWN, cal.GAZE_UD_CENTRE, cal.GAZE_UD_UP,
        ]
        for value in positions:
            self.assertGreaterEqual(value, cal.PULSE_MIN_TICKS)
            self.assertLessEqual(value, cal.PULSE_MAX_TICKS)

    def test_the_window_matches_the_datasheet(self):
        microseconds = 1_000_000 / (50 * 4096)
        self.assertAlmostEqual(cal.PULSE_MIN_TICKS * microseconds, 537, delta=5)
        self.assertAlmostEqual(cal.PULSE_MAX_TICKS * microseconds, 2500, delta=5)


class TestLids(unittest.TestCase):
    def test_shut_and_open_differ_on_every_lid(self):
        for index, lid in enumerate(LIDS):
            self.assertNotEqual(cal.LID_SHUT[index], cal.LID_OPEN[index], lid)

    def test_the_upper_lids_travel_further_than_the_lower_ones(self):
        # Geometry, not calibration: the lower lids sit on a shorter arm, so a
        # lower pair that out-travels its upper pair means two values swapped.
        for upper, lower in ((0, 1), (2, 3)):
            self.assertGreater(
                abs(cal.LID_OPEN[upper] - cal.LID_SHUT[upper]),
                abs(cal.LID_OPEN[lower] - cal.LID_SHUT[lower]),
            )

    def test_each_lid_opens_the_way_its_servo_faces(self):
        # The two eyes mirror each other, so their servos turn opposite ways:
        # the left upper and right lower lids open toward higher ticks, the
        # other two toward lower. Swapping one lid's pair keeps its travel the
        # same length and is invisible to every other check here.
        opens_upward = {"TL": True, "BL": False, "TR": False, "BR": True}
        for index, lid in enumerate(LIDS):
            upward = cal.LID_OPEN[index] > cal.LID_SHUT[index]
            self.assertEqual(upward, opens_upward[lid], lid)

    def test_lid_ticks_reaches_both_ends(self):
        self.assertEqual(cal.lid_ticks(0.0), tuple(cal.LID_OPEN))
        self.assertEqual(cal.lid_ticks(1.0), tuple(cal.LID_SHUT))

    def test_half_closed_lands_between_the_ends(self):
        for index, value in enumerate(cal.lid_ticks(0.5)):
            low = min(cal.LID_OPEN[index], cal.LID_SHUT[index])
            high = max(cal.LID_OPEN[index], cal.LID_SHUT[index])
            self.assertGreater(value, low)
            self.assertLess(value, high)


class TestGaze(unittest.TestCase):
    def test_centres_lie_between_their_edges(self):
        self.assertLess(cal.GAZE_LR_LEFT, cal.GAZE_LR_CENTRE)
        self.assertLess(cal.GAZE_LR_CENTRE, cal.GAZE_LR_RIGHT)
        self.assertLess(cal.GAZE_UD_DOWN, cal.GAZE_UD_CENTRE)
        self.assertLess(cal.GAZE_UD_CENTRE, cal.GAZE_UD_UP)

    def test_reach_stays_inside_the_measured_edges(self):
        self.assertGreaterEqual(cal.GAZE_LR_CENTRE - cal.GAZE_LR_REACH, cal.GAZE_LR_LEFT)
        self.assertLessEqual(cal.GAZE_LR_CENTRE + cal.GAZE_LR_REACH, cal.GAZE_LR_RIGHT)
        self.assertGreaterEqual(cal.GAZE_UD_CENTRE - cal.GAZE_UD_REACH_DOWN, cal.GAZE_UD_DOWN)
        self.assertLessEqual(cal.GAZE_UD_CENTRE + cal.GAZE_UD_REACH_UP, cal.GAZE_UD_UP)


if __name__ == "__main__":
    unittest.main()
