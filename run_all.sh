#!/usr/bin/env bash
#
# Copyright 2026 by Ichiro Furusato. All rights reserved. This file is part
# of the HS Ontology Converter project, released under the MIT License.
# Please see the LICENSE file included as part of this package.
#
# author:   Ichiro Furusato
# created:  2026-03-16
# modified: 2026-03-16
#
# run_all.sh — Generate all HS ontology files and run validation and audit.
#
# This script reproduces the complete pipeline from source CSV files to
# validated ontology YAML files and a data quality audit report.
#
# Prerequisites:
#   - Python 3.10 or later
#   - PyYAML (sudo apt install python3-yaml  OR  pip install pyyaml)
#   - NZ Customs tariff CSV files in the current directory (or --input-dir)
#     Download: https://www.customs.govt.nz/business/tariffs/tariff-classifications-and-rates/
#
# Usage:
#   ./run_all.sh
#   ./run_all.sh --input-dir /path/to/csvs
#
# Output:
#   ./ontology/           Current-only ontology YAML files
#   ./ontology_history/   Full historical ontology YAML files
#   ./audit_report.csv    Data quality audit report
#

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

INPUT_DIR="./data"
ONTOLOGY_DIR="./ontology"
HISTORY_DIR="./ontology_history"
AUDIT_REPORT="./audit_report.csv"
PYTHON="${PYTHON:-python3}"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input-dir|-i)
            INPUT_DIR="$2"
            shift 2
            ;;
        --python)
            PYTHON="$2"
            shift 2
            ;;
        --help|-h)
            head -30 "$0" | grep "^#" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STEP=0

step() {
    STEP=$((STEP + 1))
    echo ""
    echo "========================================"
    echo "  Step $STEP: $1"
    echo "========================================"
}

check_file() {
    if [[ ! -f "$1" ]]; then
        echo "ERROR: Required file not found: $1" >&2
        echo "Download source data from:" >&2
        echo "  https://www.customs.govt.nz/business/tariffs/tariff-classifications-and-rates/" >&2
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

step "Preflight checks"

echo "  Python:    $("$PYTHON" --version)"
echo "  Input dir: $INPUT_DIR"

# Check required CSV files
for f in Tariff_Details.csv Tariff_Rates.csv Tariff_Levies.csv Tariff_Levy_Formulas.csv; do
    check_file "$INPUT_DIR/$f"
    SIZE=$(du -h "$INPUT_DIR/$f" | cut -f1)
    echo "  Found:     $f ($SIZE)"
done

# Check PyYAML available (needed for validate.py)
if ! "$PYTHON" -c "import yaml" 2>/dev/null; then
    echo ""
    echo "  WARNING: PyYAML not found — validate.py will fail."
    echo "  Install with: sudo apt install python3-yaml"
    echo "  Continuing anyway (convert and audit will still run)..."
fi

# ---------------------------------------------------------------------------
# Step 1: Data quality audit
# ---------------------------------------------------------------------------

step "Data quality audit → $AUDIT_REPORT"

# Allow non-zero exit — findings are expected and do not prevent generation
"$PYTHON" audit.py \
    --input-dir "$INPUT_DIR" \
    --output "$AUDIT_REPORT" || {
    echo ""
    echo "  NOTE: Audit found data quality issues in source CSVs."
    echo "  Review $AUDIT_REPORT for details."
    echo "  Continuing with ontology generation..."
}

# ---------------------------------------------------------------------------
# Step 2: Generate current-only ontology
# ---------------------------------------------------------------------------

step "Generate current-only ontology → $ONTOLOGY_DIR"

"$PYTHON" convert.py \
    --all \
    --input-dir "$INPUT_DIR" \
    --output-dir "$ONTOLOGY_DIR"

# ---------------------------------------------------------------------------
# Step 3: Generate full historical ontology
# ---------------------------------------------------------------------------

step "Generate historical ontology → $HISTORY_DIR"

"$PYTHON" convert.py \
    --all \
    --include-history \
    --input-dir "$INPUT_DIR" \
    --output-dir "$HISTORY_DIR"

# ---------------------------------------------------------------------------
# Step 4: Validate current-only ontology
# ---------------------------------------------------------------------------

step "Validate current-only ontology"

"$PYTHON" validate.py "$ONTOLOGY_DIR" || {
    echo ""
    echo "  WARNING: Validation found errors in current ontology."
    echo "  Review the output above before using these files."
}

# ---------------------------------------------------------------------------
# Step 5: Validate historical ontology
# ---------------------------------------------------------------------------

step "Validate historical ontology"

"$PYTHON" validate.py "$HISTORY_DIR" || {
    echo ""
    echo "  WARNING: Validation found errors in historical ontology."
    echo "  Review the output above before using these files."
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "========================================"
echo "  Complete."
echo "========================================"
echo ""
echo "  Output files:"
echo ""

for f in \
    "$ONTOLOGY_DIR/hs.yaml" \
    "$ONTOLOGY_DIR/tariff_details.yaml" \
    "$ONTOLOGY_DIR/tariff_levies.yaml" \
    "$ONTOLOGY_DIR/tariff_levy_formulas.yaml" \
    "$ONTOLOGY_DIR/tariff_rates.yaml" \
    "$HISTORY_DIR/hs.yaml" \
    "$HISTORY_DIR/tariff_details.yaml" \
    "$HISTORY_DIR/tariff_levies.yaml" \
    "$HISTORY_DIR/tariff_levy_formulas.yaml" \
    "$HISTORY_DIR/tariff_rates.yaml" \
    "$AUDIT_REPORT"
do
    if [[ -f "$f" ]]; then
        SIZE=$(du -h "$f" | cut -f1)
        printf "    %-55s %s\n" "$f" "$SIZE"
    fi
done

echo ""

#EOF
