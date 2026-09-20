#!/usr/bin/env bash
# Run the offline suite. No board, no servos, no network.
#
#     tests/run.sh
#     tests/run.sh -v
#     tests/run.sh test_server
#
# -B stops Python writing bytecode. A calibration edit that keeps the file the
# same length, 350 for 170, can otherwise be served from a stale .pyc and the
# suite passes against code that is no longer on disk.

set -euo pipefail

cd "$(dirname "$0")"
exec python3 -B -m unittest discover "$@"
