#!/usr/bin/env python3
"""Write secrets.py to the board.

Run this yourself. The password is typed at a hidden prompt, held in memory and
in a file only this user can read, then deleted. It never reaches a command
line, the shell history, or the process list.

    python3 provision-wifi.py

Set PORT to override the default serial device.
"""

import getpass
import os
import subprocess
import sys
import tempfile

PORT = os.environ.get("PORT", "/dev/cu.usbserial-0001")


def main() -> int:
    ssid = input("SSID: ").strip()
    if not ssid:
        print("SSID cannot be empty", file=sys.stderr)
        return 1

    password = getpass.getpass("Password: ")
    if not password:
        print("Password cannot be empty", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "secrets.py")
        # Open with 0600 before writing, so the password is never briefly
        # readable by another account on this machine.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write("SSID = %r\n" % ssid)
            handle.write("PASSWORD = %r\n" % password)

        result = subprocess.run(
            ["mpremote", "connect", PORT, "fs", "cp", path, ":secrets.py"],
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        print("\nIs the board plugged in, and is %s the right port?" % PORT, file=sys.stderr)
        return result.returncode

    print("secrets.py written to the board on %s" % PORT)
    print("Tell Claude it is done; nothing else on your side.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
