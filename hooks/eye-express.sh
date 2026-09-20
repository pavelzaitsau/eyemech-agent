#!/usr/bin/env bash
# Play an expression on the animatronic eye when a session wants attention.
#
#     eye-express.sh alert        a questionnaire is waiting
#     eye-express.sh suspicious   a command is asking permission
#
# The eye is a nicety, so this never blocks and never fails a session: any
# error ends the script quietly. The server answers only once the gesture
# finishes, so the overall timeout is generous; the one-second connect timeout
# is what keeps an unplugged eye from holding the hook open for six.

EYE_URL="${EYE_URL:-http://192.168.1.210}"
EXPRESSION="${1:-alert}"

curl -s -m 6 --connect-timeout 1 -o /dev/null \
  -X POST "$EYE_URL/express" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"$EXPRESSION\"}" || exit 0

exit 0
