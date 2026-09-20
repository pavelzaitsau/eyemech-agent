#!/usr/bin/env bash
# Copy the firmware onto the board and restart it.
#
#     tools/deploy.sh
#     PORT=/dev/cu.usbmodem1234 tools/deploy.sh
#
# secrets.py is not sent: it holds the network credentials and belongs only on
# the board. Write it with tools/provision-wifi.py.

set -euo pipefail

PORT="${PORT:-/dev/cu.usbserial-0001}"
FIRMWARE="$(cd "$(dirname "$0")/../firmware" && pwd)"

if ! command -v mpremote >/dev/null; then
  echo "mpremote is not installed: brew install mpremote" >&2
  exit 1
fi

# calibration first, then its dependants, then the entry point. The order only
# matters if the copy is interrupted: the board is then left without a main.py
# rather than with one that imports a module it has not received.
for file in calibration.py eyemech.py wifi.py server.py main.py; do
  echo "-> $file"
  mpremote connect "$PORT" fs cp "$FIRMWARE/$file" ":$file"
done

echo "-> reset"
mpremote connect "$PORT" reset

echo
echo "The board prints its address a few seconds after boot."
