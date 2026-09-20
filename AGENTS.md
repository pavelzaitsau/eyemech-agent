# Agent instructions

This repository drives a physical animatronic eye. Code that passes every test
can still leave six servos motionless. The rules below cover the gap between a
green run and a working eye.

Read [README.md](README.md) for the hardware, the wiring and the control
surface. This file covers only how to work on it.

## The eye is real

A green test run proves the logic, not the motion. The suite fakes the I2C bus,
so it cannot see a servo that never moved.

Two failures look exactly like working firmware, and each cost hours before
anyone found it:

- **The PCA9685 returns to 200 Hz after a power cycle.** Every command then
  lands near 460 us, below the MG90S minimum, and nothing moves. `Eye.configure`
  sets prescale 121 on every run for that reason. Do not remove it.
- **The servo rail can be unpowered while the logic side answers normally.**
  `GET /state` reports `pwm_lr` and `pwm_ud` read back out of the chip, which
  makes the difference visible. Trust those over the commanded values.

Confirm motion by eye, or by a state read, before reporting that something
works.

## Positions are ticks, never degrees

Every position in `firmware/calibration.py` is a PCA9685 pulse width. The
upstream helper mapped 0 to 180 degrees onto 732 to 2929 us, past both ends of
the MG90S window. A servo driven past its stop presses into the printed part
without a sound.

Both ends of every axis sit 12 ticks short of the mechanical stop. That margin
is where the hum stops, so do not widen a limit without measuring it on the
mechanism.

## Stillness is the default

The eye holds its pose and never starts moving on its own. Movement means a
session is waiting on an answer, and an eye that drifts between times spends
that signal on nothing.

Idle behaviour exists and is off by default in `firmware/server.py`. Turn it on
only when asked.

## Before a change lands

```bash
tests/run.sh
```

The suite is offline: no board, no servos, no network. Deploying needs the board
on USB:

```bash
tools/deploy.sh
```

`secrets.py` holds the Wi-Fi credentials, lives only on the board, and is
ignored by git. Never write it into the repository, a log or a command line.
`tools/provision-wifi.py` prompts for the password and writes it to the board.

## Writing

Prose, commit bodies and code comments follow the skills vendored under
`.claude/skills/`: `technical-writing` for prose, `markdown-formatting` for
Markdown, `commit-messages` for commits. Invoke the skill rather than working
from memory.

Commits follow Conventional Commits. No attribution footer of any kind: no
`Co-Authored-By`, no `Generated with`, no tool credit.

## Hooks

`hooks/` holds the Claude Code hooks that make the eye signal a waiting session,
and `tools/install-hooks.sh` installs them.

Claude Code reads hooks at session start, and a new session inside a running app
does not reread them. Quit the app and start it again after changing one.
