"""Measured servo limits for the EyeMech e3.2 mechanism.

Every position is a PCA9685 tick, not a degree. One tick is 1/4096 of the PWM
period; at prescale 121 the period is 50.0 Hz, so one tick is 4.88 us.

Degrees are absent on purpose. The upstream firmware maps 0-180 degrees to
150-600 ticks, which is 732-2929 us. An MG90S accepts 500-2500 us, so any
command above 140 degrees drives the servo into its internal end stop, where it
stalls without an audible bind. Ticks remove that trap.

The four lid values come from a physical sweep on 2026-09-19: each lid moved
one step at a time until it reached the closing line or the end of its travel.
They are specific to this mechanism and to how each horn sits on its spline.
Refitting a horn invalidates that channel's pair.

The gaze axes were measured the same way on 2026-09-20. Neither centre sits at
the middle of its travel, because neither horn sits square on its spline. Both
axes therefore reach further one way than the other.
"""

I2C_SCL_PIN = 22
I2C_SDA_PIN = 21
I2C_FREQ_HZ = 400_000

PCA9685_ADDR = 0x40
PCA9685_PRESCALE = 121  # 50.0 Hz
LED0_BASE_REG = 0x06

# The MG90S datasheet window, in ticks. Outside it the servo stalls silently.
PULSE_MIN_TICKS = 110  # 537 us
PULSE_MAX_TICKS = 512  # 2500 us

CH_LR, CH_UD, CH_TL, CH_BL, CH_TR, CH_BR = range(6)

# Index by channel: (TL, BL, TR, BR) for lids 2-5.
#
# Both ends sit 12 ticks short of where the lid stops moving. At the stop
# itself every one of the four servos hums, which is a stalled motor pressing
# into the mechanism. A blink holds each end several times a minute, so the
# stop is not a safe target on either side.
LID_SHUT = (224, 350, 350, 130)
LID_OPEN = (425, 212, 170, 248)

# Each edge sits 12 ticks short of the mechanical stop, as the lids do.
GAZE_LR_LEFT = 187
GAZE_LR_CENTRE = 300
GAZE_LR_RIGHT = 438

GAZE_UD_DOWN = 252
GAZE_UD_CENTRE = 368
GAZE_UD_UP = 438

# How far the gaze actually travels from centre, which is less than the
# mechanism allows. Horizontally the shorter side sets the limit. Downward the
# mechanism reaches 116 ticks, and that much looks wrong on the finished eye,
# so the downward reach matches the upward one.
GAZE_LR_REACH = 113
GAZE_UD_REACH_UP = 70
GAZE_UD_REACH_DOWN = 70

# A blink interpolates every lid along the same fraction of its own travel, so
# the two halves of each eye meet at one moment despite unequal spans.
BLINK_STEPS = 14
BLINK_STEP_MS = 5
BLINK_HOLD_MS = 80

# 93 ms is the floor for this mechanism. A 37 ms profile leaves the lids short
# of the closing line: the servo cannot cross 90 degrees in that time, so the
# eye never shuts.
BLINK_CLOSE_MS = 93


def lid_ticks(fraction):
    """Return the four lid positions at `fraction` of the way from open to shut.

    `fraction` runs 0.0 (open) to 1.0 (shut). Values between the two give a
    squint. The result is ordered (TL, BL, TR, BR), matching channels 2-5.
    """
    return tuple(
        int(LID_OPEN[i] + (LID_SHUT[i] - LID_OPEN[i]) * fraction)
        for i in range(4)
    )


def frame(i2c, lr, ud, fraction):
    """Write all six channels in one transaction.

    Channel registers run contiguously from 0x06, so a single 24-byte write
    with auto-increment enabled moves every servo at the same instant. Separate
    writes let one lid lead the other by a visible margin.
    """
    buf = bytearray(24)
    for i, value in enumerate((int(lr), int(ud)) + lid_ticks(fraction)):
        buf[i * 4 + 2] = value & 0xFF
        buf[i * 4 + 3] = value >> 8
    i2c.writeto_mem(PCA9685_ADDR, LED0_BASE_REG, buf)


def configure(i2c):
    """Wake the chip and set 50 Hz.

    Call this at the start of every session. The chip returns to its power-on
    defaults between sessions, and its default prescale of 30 gives 200 Hz. At
    200 Hz a servo command lands near 460 us, below the MG90S minimum, and no
    servo moves at all while the I2C bus still reports every write as accepted.
    """
    i2c.writeto_mem(PCA9685_ADDR, 0x00, bytes([0x10]))
    i2c.writeto_mem(PCA9685_ADDR, 0xFE, bytes([PCA9685_PRESCALE]))
    i2c.writeto_mem(PCA9685_ADDR, 0x00, bytes([0x00]))
    i2c.writeto_mem(PCA9685_ADDR, 0x00, bytes([0xA0]))


def release(i2c, channel):
    """Stop driving one channel.

    Setting the full-off bit removes the pulse train, and the servo goes limp
    within one period. Use this the moment a servo hums against a stop: a
    stalled MG90S draws its full current and heats its gearbox.
    """
    reg = LED0_BASE_REG + 4 * channel
    i2c.writeto_mem(PCA9685_ADDR, reg, bytes([0, 0, 0, 0x10]))
