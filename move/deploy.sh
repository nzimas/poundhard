#!/bin/bash
# One-shot deploy of everything PoundHard needs to the Move.
#   1. SC runtime bundle (reused from wildrider)  — deploy-bundle.sh
#   2. controller + engine .scd + run scripts     — deploy-controller.sh
#   3. Schwung overtake module (ui.js)            — deploy-module.sh
# Usage: ./deploy.sh [move-host]   (default: move.local)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${1:-move.local}"

echo "=== 1/3 SC bundle ==="
"$HERE/deploy-bundle.sh" "$HOST" || echo "(bundle step failed — provision it manually; see deploy-bundle.sh)"
echo "=== 2/3 controller + engine ==="
"$HERE/deploy-controller.sh" "$HOST"
echo "=== 3/3 Schwung module ==="
"$HERE/deploy-module.sh" "$HOST"
echo
echo "All deployed. On the Move: open Schwung -> overtake -> PoundHard."
