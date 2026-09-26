#!/usr/bin/env bash
# Tamper demo: a signed log verifies ✅; change ONE wait_s and it fails ❌.
#   bash hardware/tools/tamper_demo.sh                    # makes a fresh demo log with the simulator
#   bash hardware/tools/tamper_demo.sh hardware/logs/cc-01.jsonl   # or use a real device log
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PYTHON:-python3}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/callclock-tamper.XXXXXX")

if [[ $# -ge 1 ]]; then
  cp "$1" "$WORK/original.jsonl"
else
  echo "Making a demo log with the simulator (no API needed)…"
  "$PY" hardware/sim/simulate_device.py --script demo --speed 1000 --no-api --out "$WORK/original.jsonl" >/dev/null
fi

echo
echo "1) The untouched log:"
"$PY" hardware/tools/verify_log.py "$WORK/original.jsonl"

echo
echo "2) Someone edits one wait to make the home look faster:"
"$PY" - "$WORK/original.jsonl" "$WORK/tampered.jsonl" <<'PYEOF'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
lines = [l.strip() for l in open(src) if l.strip()]
out, done = [], False
for l in lines:
    prefix = l[:4] if l[:4] in ("EVT ", "LOG ") else ""
    ev = json.loads(l[len(prefix):])
    if not done and ev.get("wait_s") is not None and ev["wait_s"] > 5:
        print(f"   seq {ev['seq']}: wait_s {ev['wait_s']} -> 3.0")
        ev["wait_s"], done = 3.0, True
    out.append(prefix + json.dumps(ev))
open(dst, "w").write("\n".join(out) + "\n")
PYEOF
if "$PY" hardware/tools/verify_log.py "$WORK/tampered.jsonl"; then
  echo "UNEXPECTED: the tampered log verified"; exit 1
fi

echo
echo "3) A smarter edit that also recomputes the hash (but has no device key):"
"$PY" - "$WORK/tampered.jsonl" "$WORK/rehashed.jsonl" <<'PYEOF'
import json, sys
sys.path.insert(0, ".")
from hardware.eventlog import compute_hash
evs = [json.loads(l[4:] if l[:4] in ("EVT ", "LOG ") else l) for l in open(sys.argv[1]) if l.strip()]
prev = None
for ev in evs:
    if prev is not None:
        ev["prev_hash"] = prev
    ev["hash"] = compute_hash(ev)
    prev = ev["hash"]
open(sys.argv[2], "w").write("".join(json.dumps(e) + "\n" for e in evs))
PYEOF
if "$PY" hardware/tools/verify_log.py "$WORK/rehashed.jsonl"; then
  echo "UNEXPECTED: the re-hashed log verified"; exit 1
fi
echo
echo "Tamper-evident, not tamper-proof: the key lives in the device's flash. Files are in $WORK"
