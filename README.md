# eyemech-agent

An animatronic eye an agent can drive.

The mechanism is Will Cogley's [EyeMech e3.2](https://github.com/will-cogley/EyeMech_Epsilon),
printed in PLA and moved by six MG90S servos. An ESP32 runs MicroPython, a
PCA9685 drives the servos, and an MCP server turns the whole thing into seven
tools a language model can call.

Ask it to look left, and it looks left. Leave it alone, and it holds still: the
eye moves when a session wants an answer, and that is the whole vocabulary.

## Layout

| Path | Contents |
| --- | --- |
| `AGENTS.md` | How to work on this repository |
| `firmware/` | What runs on the board |
| `mcp-server/` | The MCP server, TypeScript over stdio |
| `hooks/` | Session hooks: how the eye reacts when a session waits |
| `tools/` | Flashing, credentials, hook install, skill refresh |
| `tests/` | An offline suite: no board, no servos |
| `.claude/skills/` | The writing rules this repository is held to |

## Hardware

| Part | Notes |
| --- | --- |
| ESP32 DevKit, 30 pin | CP2102 bridge; USB powers the logic |
| PCA9685 | 16-channel PWM driver, address `0x40` |
| MG90S servo, 180 degrees | Six: two for gaze, four for the lids |
| USB-C PD trigger | 5 V for the servo rail, separate from the ESP32 |
| Electrolytic capacitor | 470 to 1000 uF across V+ and GND |

The mechanism needs no screws beyond the horn screws each servo ships with.
Print the `ServoSizingPlate` first and fit a servo to it: that tells you whether
to print variant A or variant B.

## Wiring

| From | To | Why |
| --- | --- | --- |
| ESP32 `3V3` | PCA9685 `VCC` | Logic supply. 5 V here pulls the I2C lines above what the ESP32 pins accept |
| ESP32 `GND` | PCA9685 `GND` | Common ground |
| ESP32 `GPIO21` | PCA9685 `SDA` | |
| ESP32 `GPIO22` | PCA9685 `SCL` | |
| PD trigger, 5 V | PCA9685 `V+` terminal | Servo rail. Six MG90S peak well past what USB supplies |
| Capacitor | Across `V+` and `GND` | Absorbs the inrush when several servos start together |

Leave `OE` unconnected; the board pulls it low and the outputs are enabled.
Never power the servos from the ESP32.

## Flashing

Install the tools, then erase and write MicroPython. The offset is `0x1000`,
not `0x0`:

```bash
brew install esptool mpremote
```

```bash
esptool --chip esp32 --port /dev/cu.usbserial-0001 erase-flash
```

```bash
esptool --chip esp32 --port /dev/cu.usbserial-0001 --baud 460800 write-flash 0x1000 ESP32_GENERIC-v1.29.0.bin
```

Download the firmware from
[micropython.org](https://micropython.org/download/ESP32_GENERIC/); it is not
kept here.

Copy the modules across and restart the board:

```bash
tools/deploy.sh
```

Then write the network credentials. The script prompts for them, so the
password never reaches the shell history or the process list:

```bash
python3 tools/provision-wifi.py
```

## Tests

```bash
tests/run.sh
```

The firmware reaches for `machine`, `network` and the MicroPython halves of
`time` and `asyncio`. `tests/shim.py` supplies all four, so the suite runs on
any machine with Python 3. Its fake I2C keeps a register file rather than
swallowing writes, which lets a test assert the ticks that reached the chip.

What the suite does not do is tell you the eye is calibrated. It proves the
table is self-consistent and inside the servo's window; only the mechanism can
say whether 224 ticks is where that lid shuts.

## Calibration

Every position in `firmware/calibration.py` is a PCA9685 tick, not a degree,
and every value was measured on one physical mechanism. **Refitting a servo
horn voids that channel's pair.**

Degrees are absent on purpose. The upstream firmware maps 0 to 180 degrees onto
150 to 600 ticks, which is 732 to 2929 us. An MG90S accepts 500 to 2500 us, so
anything above 140 degrees drives the servo into its own end stop, where it
stalls without an audible bind.

Both ends of every axis sit 12 ticks short of where the mechanism stops. At the
stop itself each servo hums, which is a stalled motor pressing into the
linkage, and a blink holds that position several times a minute.

Two failures during the build looked exactly like working firmware:

- The PCA9685 returns to 200 Hz after any power cycle. At 200 Hz a servo
  command lands near 460 us, below the MG90S minimum, so nothing moves while
  the I2C bus still acknowledges every write.
- The servo rail was left unpowered while the logic side answered normally.

Neither is visible from the commanded side, which is why `GET /state` reads
`pwm_lr` and `pwm_ud` back out of the PCA9685. Values that track the command
prove the signal is leaving the chip; a still eye then means the servo rail has
no supply. A value of 4096 is the full-off bit, and no pulse at all.

## Control surface

The board serves seven endpoints on port 80:

| Request | Body | Effect |
| --- | --- | --- |
| `POST /look` | `{"x": -1..1, "y": -1..1}` | Points the gaze and holds it |
| `POST /blink` | `{"ms": 93}`, optional | Closes and reopens the lids once |
| `POST /wink` | `{"side": "left"}` | Closes and reopens one eye |
| `POST /express` | `{"name": "alert"}` | Plays a gesture and returns to the pose |
| `POST /squint` | `{"v": 0..1}` | Holds the lids partly closed |
| `POST /idle` | `{"enabled": true}` | Switches idle behaviour on or off |
| `GET /state` | | Reports gaze, squint, mode, the ticks the chip holds, and the Wi-Fi reconnect count |

Coordinates run -1 to 1 on each axis. The lids follow the vertical gaze without
being asked: looking down draws the upper lids after the pupil, looking up
raises the lower lids a little.

A blink under 93 ms leaves the lids short of each other, because the servo
cannot cross the upper lid's travel any faster.

## Expressions

Four gestures, each a scripted run of gaze and lid moves that ends where it
began. A held squint survives one, and a command arriving mid-gesture cuts it
short rather than queueing behind a second of theatre.

| Name | Reads as |
| --- | --- |
| `alert` | Wide and still, then two fast blinks. Asking for attention |
| `suspicious` | Lids to a slit, one slow sweep across, no blink |
| `curious` | A glance up and away, a blink on the return |
| `tired` | Heavy lids, the gaze sagging, one long blink |

## Reacting to a session

The eye asks for attention whenever a Claude Code session is waiting on you. It
keeps asking every 5 to 10 seconds until you answer.

| What is waiting | Gesture |
| --- | --- |
| A questionnaire with options | `alert` |
| A command asking permission | `suspicious` |

Install the hooks, then quit the app and start it again:

```bash
tools/install-hooks.sh
```

Claude Code fires an event when a dialog opens and none when it closes, so the
loop cannot wait for an answer. Three hooks end it instead: `PostToolUse`,
`UserPromptSubmit` and `Stop`. Each fires when the session has moved on.

A 10-minute deadline ends a loop that none of the three reached. Without it, a
missed event leaves the eye gesturing until someone unplugs the board.

Each session nags under its own key. Answering in one session leaves another
session's question still calling, which is the point of keying them apart.

To silence every loop at once:

```bash
~/.claude/hooks/eye-nag-stop.sh --all
```

## Idle behaviour

The eye is still by default. It holds its pose until something moves it, and it
never starts moving on its own. Movement means a session is waiting, so an eye
that drifts for its own sake spends the signal on nothing.

`POST /idle` with `true` turns autonomous movement on for as long as the board
stays powered: with no command for 8 seconds the eye saccades to random targets,
fixates for 300 ms to 1500 ms, drifts a little, and blinks every two to four
seconds. Any command interrupts that within about 40 ms.

The setting lives in memory, so a power cycle returns the eye to still.

The loop catches its own exceptions and reports them as `idle_error` in
`GET /state`. An uncaught one used to end the background task outright, and
asyncio swallows the traceback: the eye went still for good while `/state` went
on reporting `idle`, which reads as working.

## When the link drops

A dropped association does not close the listening socket, so the board goes on
serving a network nobody can reach it from: from outside it is simply gone. A
background task re-associates every 5 seconds until it succeeds, and `/state`
carries `wifi_reconnects` so a recovered drop leaves a trace rather than
vanishing.

## MCP server

Build it, then register it with the address the board prints on boot:

```bash
cd mcp-server && npm install && npm run build
```

```bash
claude mcp add eye --env EYE_URL=http://192.168.1.210 -- node "$PWD/mcp-server/dist/index.js"
```

A later rebuild reaches the client only after the Claude Code app restarts.
[After a rebuild](mcp-server/README.md#after-a-rebuild) says why a new session
is not enough.

Seven tools follow: `eye_look`, `eye_blink`, `eye_wink`, `eye_express`,
`eye_squint`, `eye_set_idle` and `eye_get_state`. Their arguments are in
[mcp-server/README.md](mcp-server/README.md).

## Security

The board serves its endpoints to the whole local network with no
authentication. Anyone who can reach the port can move the eye. That suits a
device on a home network; putting it on a shared one means adding a check to
`firmware/server.py` first.

`secrets.py` holds the network credentials. It is written straight to the board
and is listed in `.gitignore`, so it never enters this repository.
