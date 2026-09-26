#!/usr/bin/env bash
# Build the Nano firmware, run it in simavr through two power cycles, and check the output:
# every live event verifies, and the final `dump` (rebuilt from EEPROM) matches the live lines byte for byte.
# Needs: sudo apt install simavr libsimavr-dev libelf-dev   (plus PlatformIO)
set -euo pipefail
cd "$(dirname "$0")/../../.."
WORK=$(mktemp -d "${TMPDIR:-/tmp}/nanosim.XXXXXX")
(cd hardware/firmware && pio run -e nano >/dev/null)
g++ -O2 -I/usr/include/simavr -o "$WORK/nanosim" hardware/tools/nanosim/nanosim.cpp \
    -lsimavr -lsimavrparts -lelf -lm -lpthread -lutil
echo "Running the Nano firmware in simavr (about 2 minutes)…"
"$WORK/nanosim" hardware/firmware/.pio/build/nano/firmware.elf "$WORK/out.txt" 2>/dev/null
grep -E "^(DBG boot Call|DBG status|EVT )" "$WORK/out.txt" | cut -c1-140
python3 - "$WORK/out.txt" <<'PY'
import json, sys
sys.path.insert(0, ".")
from hardware.eventlog import load_keys, verify_chain
lines = open(sys.argv[1]).read().splitlines()
evt = [l[4:] for l in lines if l.startswith("EVT ")]
dumps, cur = [], []
for l in lines:
    if l.startswith("LOG "):
        cur.append(l[4:])
    elif l == "DBG dump end":
        dumps, cur = dumps + [cur], []
res = verify_chain([json.loads(l) for l in evt], load_keys())
assert len(evt) == 10, f"expected 10 events, got {len(evt)}"
assert res["ok"], res
assert dumps and dumps[-1] == evt, "dump rebuilt from EEPROM differs from the live lines"
print(f"✅ {len(evt)} events across a power cycle verify; the EEPROM dump matches the live lines byte for byte")
PY
