#!/bin/bash
# Reproduction script for KPI-BENCH-10: SUBOFF/DTMB5415/KVLCC2 resistance benchmarks
# Usage: bash benchmarks/cases/repro.sh
#
# This script runs all three benchmark cases and produces result JSON files
# in tensorbench-runs/<case>/ directories.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "=== KPI-BENCH-10: Resistance Benchmark Reproduction ==="
echo "Repository: $REPO_ROOT"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

CASES="suboff dtmb5415 kvlcc2"

for case in $CASES; do
    echo "--- Running $case ---"
    python3 -c "
from tensorbench.cli import main
import sys
sys.argv = ['tensorbench', 'run', '--spec', 'benchmarks/cases/$case/spec.json', '--output', 'tensorbench-runs/$case']
main()
" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
ct = fn = None
for m in data.get('metrics', []):
    if m['name'] == 'Ct': ct = m['value']
    if m['name'] == 'Fn': fn = m['value']
status = data.get('acceptance', {}).get('status', 'unknown')
print(f'  Ct={ct:.6e}, Fn={fn:.4f}, status={status}')
"
    echo ""
done

echo "=== Results Summary ==="
echo "Results stored in: tensorbench-runs/<case>/*.result.json"
echo ""
echo "To compare with experimental values:"
echo "  python3 benchmarks/cases/compare_results.py"
