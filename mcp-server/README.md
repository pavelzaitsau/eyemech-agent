# eye-mcp-server

An MCP server that gives an agent control of the EyeMech e3.2 animatronic eye.

The eye runs MicroPython on an ESP32 and serves four HTTP endpoints on the local
network. This server wraps them as tools over stdio.

## Requirements

- Node 18 or newer
- The eye powered, joined to the network, and running `firmware/main.py`

## Setup

```bash
npm install
npm run build
```

The board prints its address on boot:

```text
eye ready on http://192.168.1.42/
```

Pass that address as `EYE_URL`. Register the server with Claude Code:

```bash
claude mcp add eye --env EYE_URL=http://192.168.1.42 -- node "$PWD/dist/index.js"
```

`EYE_URL` is read per call, not at startup. Powering the board after the client
starts costs one failed call, not a restart.

### After a rebuild

Quit the Claude Code app and start it again. A rebuilt `dist/` does not reach a
running client, which holds one server process and one cached tool list for as
long as the app runs.

A new session reuses both. Killing the process does not help either: the app
respawns it from the new build, then serves the cached list anyway. A tool added
since the app started stays missing until the app restarts.

## Tools

| Tool | Effect | Read-only |
| --- | --- | --- |
| `eye_look` | Points the gaze and holds it | No |
| `eye_blink` | Closes and reopens both lids once | No |
| `eye_wink` | Closes and reopens one eye | No |
| `eye_express` | Plays a gesture: alert, suspicious, curious, tired | No |
| `eye_squint` | Holds the lids partly closed | No |
| `eye_set_idle` | Switches the eye's own idle behaviour on or off | No |
| `eye_get_state` | Reports gaze, squint and mode | Yes |

Every tool takes `response_format`, either `markdown` (default) or `json`.

### eye_look

Takes `x` from -1 (left) to 1 (right) and `y` from -1 (down) to 1 (up). Both
eyeballs move together, because the mechanism drives the pair from one servo.

The lids follow the vertical gaze without being asked: looking down draws the
upper lids after the pupil, looking up raises the lower lids a little.

```json
{"x": -0.7, "y": 0.6}
```

### eye_blink

Takes `ms`, the closing time, from 93 to 400. The whole blink runs about three
times that: closing, 80 ms shut, then opening.

Values under 93 ms are rejected. The servo cannot cross the upper lid's travel
any faster, so a shorter blink leaves a gap the viewer still sees through.

### eye_wink

Takes `side`, either `left` or `right` as the viewer sees it, and the same `ms`
as a blink. A held squint stays on the eye that is not winking.

### eye_express

Takes `name`: `alert`, `suspicious`, `curious` or `tired`. Each is a scripted
run of gaze and lid moves lasting one to two seconds, ending at the pose it
started from. The call returns when the gesture finishes.

### eye_squint

Takes `v` from 0 (open) to 1 (shut), and holds it until changed. A blink still
reaches full closure over a held squint, then returns to it.

### eye_set_idle

Takes `enabled`. The eye is still by default; true lets it move on its own,
false holds the last commanded pose again. The other tools keep working either
way.

The setting lives in memory, so a power cycle returns the eye to still.

### eye_get_state

Returns the gaze, the held squint, the raw servo ticks, and the mode:

```json
{"x": 0.0, "y": 0.0, "squint": 0.0, "lr_ticks": 300, "ud_ticks": 368, "mode": "idle"}
```

In `idle` mode the values change between calls, because the eye saccades and
drifts on its own. Two identical reads mean it is `driven`, not broken.

## Idle behaviour

The eye holds still unless `eye_set_idle` turns idle behaviour on. Movement is
how it says a session is waiting on an answer, and an eye that fidgets between
times drains that of meaning.

With idle behaviour on, 8 seconds without a command start it saccading to random
targets, fixating for 300 ms to 1500 ms, drifting a little, and blinking every
two to four seconds. Any command interrupts that within about 40 ms.

## Security

The eye serves its endpoints to the whole local network with no authentication.
Anyone who can reach the port can move it. That suits a device on a home
network; putting the eye on a shared one means adding a check to
`firmware/server.py` first, because this server sends no credentials.

## Troubleshooting

| Message | Cause |
| --- | --- |
| `EYE_URL is not set` | The variable is missing from the server's environment |
| `Cannot reach the eye at ...` | The board is off, not on the network, or at another address |
| `The eye refused ... with 400` | An argument fell outside the range the board accepts |

When every call times out but the board looks alive, check that it printed an
address at boot. Without `secrets.py` it runs idle behaviour and never starts
the server; `tools/provision-wifi.py` writes that file.
