#!/usr/bin/env bash
# PostToolUse hook: after an Edit/Write on a .py file under src/ or tests/, run the test suite.
# Exit 2 sends the failing output back to the agent so it fixes the code before moving on.
f=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')
case "$f" in
  */src/*.py|*/tests/*.py) ;;
  *) exit 0 ;;
esac
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0
if ! out=$(make test 2>&1); then
  echo "make test failed after editing $f:" >&2
  echo "$out" | grep -E "^(FAIL|ERROR|AssertionError|Traceback|  File|[A-Za-z]+Error|Ran|FAILED)" | tail -40 >&2
  exit 2
fi
