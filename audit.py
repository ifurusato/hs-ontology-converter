#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2026 by Ichiro Furusato. All rights reserved. This file is part
# of the HS Ontology Converter project, released under the MIT License.
# Please see the LICENSE file included as part of this package.
#
# author:   Ichiro Furusato
# created:  2026-03-16
# modified: 2026-03-16
#
# audit.py — Data quality audit of NZ Customs tariff source CSV files.
# 
# Checks the raw source data for anomalies and writes a structured CSV
# report suitable for internal review by NZ Customs Service.
# 
# Each finding is recorded with:
#     file       — source CSV filename
#     code       — the HS code key involved (L1+L2+L3+L4+L5+Letter)
#     check      — the name of the check that fired
#     severity   — ERROR, WARNING, or INFO
#     detail     — human-readable description of the finding
# 
# Severity levels
# ---------------
#     ERROR    — almost certainly wrong; likely a data entry or housekeeping
#                error (e.g. validFrom after validTo, duplicate rows)
#     WARNING  — possibly wrong; unusual pattern that may have a legitimate
#                explanation (e.g. one-day transition rows, orphaned rates)
#     INFO     — noteworthy but not necessarily wrong; for NZ Customs awareness
# 
# Usage
# -----
#     python audit.py [--input-dir DIR] [--output FILE]
# 
#     python audit.py
#     python audit.py --input-dir ./data --output audit_report.csv
#

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import NamedTuple


DELIMITER = "~"
SENTINEL_EXPIRY = "3000"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Finding(NamedTuple):
    file:     str
    code:     str
    check:    str
    severity: str
    detail:   str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a ~-delimited Windows-1252 CSV file."""
    rows = []
    with open(path, encoding="cp1252", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=DELIMITER)
        for row in reader:
            rows.append({k.strip(): v.strip() for k, v in row.items()})
    return rows


def parse_date(raw: str) -> datetime | None:
    """Parse NZ Customs date string to date-only datetime (for display/comparison)."""
    import re
    raw = re.sub(r"\s+", " ", raw.strip())
    raw_date = raw.split(" 12:00")[0].split(" 11:59")[0].strip()
    # Also strip other time patterns like 9:28AM, 9:29AM
    raw_date = re.sub(r"\s+\d+:\d+[AP]M$", "", raw_date).strip()
    try:
        return datetime.strptime(raw_date, "%b %d %Y")
    except ValueError:
        return None


def parse_datetime(raw: str) -> datetime | None:
    """Parse NZ Customs date string preserving time component, for sorting."""
    import re
    raw = re.sub(r"\s+", " ", raw.strip())
    for fmt in [
        "%b %d %Y %I:%M%p",    # Jan  1 2002 12:00AM
        "%b %d %Y %I:%M%p",    # Nov  3 2001  9:28AM (after space normalise)
    ]:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    # Fall back to date-only
    return parse_date(raw)


def is_sentinel(raw: str) -> bool:
    return SENTINEL_EXPIRY in raw


def code_key(row: dict, prefix: str) -> str:
    """Build the full 10-digit+letter code key from a row."""
    l1 = row.get(f"{prefix} Tariff Level 1", "")
    l2 = row.get(f"{prefix} Tariff Level 2", "")
    l3 = row.get(f"{prefix} Tariff Level 3", "")
    l4 = row.get(f"{prefix} Tariff Level 4", "")
    l5 = row.get(f"{prefix} Tariff Level 5", "")
    lt = row.get(f"{prefix} Tariff Letter", "")
    return f"{l1}{l2}{l3}{l4}{l5}{lt}"


def item_key(row: dict, prefix: str) -> str:
    """Build the 8-digit tariff item key (L1+L2+L3+L4) from a row."""
    l1 = row.get(f"{prefix} Tariff Level 1", "")
    l2 = row.get(f"{prefix} Tariff Level 2", "")
    l3 = row.get(f"{prefix} Tariff Level 3", "")
    l4 = row.get(f"{prefix} Tariff Level 4", "")
    return f"{l1}{l2}{l3}{l4}"


# ---------------------------------------------------------------------------
# Audit checks
# ---------------------------------------------------------------------------

def check_tariff_details(rows: list[dict]) -> list[Finding]:
    findings = []
    filename = "Tariff_Details.csv"
    p = "Tic"

    # Group by code key for amendment chain checks
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        k = code_key(row, p)
        groups[k].append(row)

    # Sort by full datetime (preserving time component) to avoid instability
    # when multiple rows share the same calendar date but differ in time.
    # e.g. "Nov 3 2001 9:28AM" must sort after "Jan 1 1988 12:00AM".
    for k in groups:
        groups[k].sort(
            key=lambda r: parse_datetime(r.get("Tic Start Date", "")) or datetime.min
        )

    seen_keys: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        k        = code_key(row, p)
        start    = row.get("Tic Start Date", "")
        expiry   = row.get("Tic Expiry Date", "")
        desc     = row.get("Tic Tariff Description", "").strip()
        l1       = row.get("Tic Tariff Level 1", "")
        l2       = row.get("Tic Tariff Level 2", "")
        l3       = row.get("Tic Tariff Level 3", "")
        l4       = row.get("Tic Tariff Level 4", "")
        l5       = row.get("Tic Tariff Level 5", "")
        sec      = row.get("Tic Tariff Section", "")

        dt_start  = parse_date(start)
        dt_expiry = parse_date(expiry) if not is_sentinel(expiry) else None

        # --- Temporal integrity ---

        # validFrom after validTo
        if dt_start and dt_expiry and dt_start > dt_expiry:
            findings.append(Finding(
                file=filename, code=k,
                check="DATE_RANGE_INVERTED",
                severity="ERROR",
                detail=f"validFrom ({start.strip()}) is after validTo ({expiry.strip()})",
            ))

        # One-day transition rows — NZ Customs uses these as a standard
        # mechanism during rate changes; flag only if also current (sentinel expiry)
        # since an active one-day row is more unusual than a historical one.
        if dt_start and dt_expiry and dt_start == dt_expiry:
            if is_sentinel(row.get("Tic Expiry Date", "")):
                sev = "WARNING"
                note = "currently active one-day row — unusual"
            else:
                sev = "INFO"
                note = "historical transition row — normal NZ Customs practice"
            findings.append(Finding(
                file=filename, code=k,
                check="ONE_DAY_ROW",
                severity=sev,
                detail=f"validFrom and validTo are the same date ({start.strip()}); "
                       f"{note}",
            ))

        # Missing description
        if not desc:
            findings.append(Finding(
                file=filename, code=k,
                check="MISSING_DESCRIPTION",
                severity="WARNING",
                detail="Tariff description is empty",
            ))

        # Malformed level lengths
        for level, val, expected in [
            ("Level 1", l1, 2), ("Level 2", l2, 2), ("Level 3", l3, 2),
            ("Level 4", l4, 2), ("Level 5", l5, 2),
        ]:
            if val and len(val) != expected:
                findings.append(Finding(
                    file=filename, code=k,
                    check="MALFORMED_CODE_LEVEL",
                    severity="ERROR",
                    detail=f"{level} '{val}' has {len(val)} digit(s); expected {expected}",
                ))

        # Missing section
        if not sec:
            findings.append(Finding(
                file=filename, code=k,
                check="MISSING_SECTION",
                severity="WARNING",
                detail="Tic Tariff Section is empty",
            ))

        # Track for duplicate detection
        row_sig = (start.strip(), expiry.strip())
        seen_keys[k].append(row_sig)

    # --- Duplicate rows (same key, same validFrom) ---
    for k, sigs in seen_keys.items():
        starts = [s[0] for s in sigs]
        dupes = {s for s in starts if starts.count(s) > 1}
        for d in sorted(dupes):
            findings.append(Finding(
                file=filename, code=k,
                check="DUPLICATE_ROW",
                severity="ERROR",
                detail=f"Multiple rows with the same code key and validFrom ({d})",
            ))

    # --- Amendment chain date continuity ---
    for k, group in groups.items():
        if len(group) < 2:
            continue
        for i in range(len(group) - 1):
            this_expiry = group[i].get("Tic Expiry Date", "")
            next_start  = group[i + 1].get("Tic Start Date", "")
            if is_sentinel(this_expiry):
                continue
            dt_this_exp  = parse_date(this_expiry)
            dt_next_start = parse_date(next_start)
            if not dt_this_exp or not dt_next_start:
                continue
            delta = (dt_next_start - dt_this_exp).days
            # NZ Customs uses 11:59PM close / 12:00AM open on the same
            # calendar date — these parse to the same date so delta=0,
            # which is correct abutment, not an overlap.
            # delta=1 is also normal (closes one day, opens the next).
            if delta > 1:
                findings.append(Finding(
                    file=filename, code=k,
                    check="AMENDMENT_CHAIN_GAP",
                    severity="WARNING",
                    detail=f"Gap of {delta} day(s) between version expiry "
                           f"({this_expiry.strip()}) and next version start "
                           f"({next_start.strip()})",
                ))
            elif delta < 0:
                findings.append(Finding(
                    file=filename, code=k,
                    check="AMENDMENT_CHAIN_OVERLAP",
                    severity="ERROR",
                    detail=f"Overlap of {abs(delta)} day(s) between version expiry "
                           f"({this_expiry.strip()}) and next version start "
                           f"({next_start.strip()}). Note: same-date transitions "
                           f"(delta=0) are normal NZ Customs practice and are not flagged.",
                ))

    # --- Referential integrity: build parent key sets ---
    all_item_keys      = set()
    all_subheading_keys = set()
    all_heading_keys   = set()
    all_chapter_keys   = set()
    all_section_keys   = set()

    for row in rows:
        l1  = row.get("Tic Tariff Level 1", "")
        l2  = row.get("Tic Tariff Level 2", "")
        l3  = row.get("Tic Tariff Level 3", "")
        l4  = row.get("Tic Tariff Level 4", "")
        sec = row.get("Tic Tariff Section", "")
        all_item_keys.add(f"{l1}{l2}{l3}{l4}")
        all_subheading_keys.add(f"{l1}{l2}{l3}")
        all_heading_keys.add(f"{l1}{l2}")
        all_chapter_keys.add(l1)
        if sec:
            all_section_keys.add(sec)

    # Check each statistical code has a valid parent tariff item
    # (In practice this is always true if levels are consistent,
    # but we check explicitly for malformed rows)
    seen_orphans: set[str] = set()
    for row in rows:
        l1 = row.get("Tic Tariff Level 1", "")
        l2 = row.get("Tic Tariff Level 2", "")
        l3 = row.get("Tic Tariff Level 3", "")
        l4 = row.get("Tic Tariff Level 4", "")
        k  = code_key(row, "Tic")
        parent = f"{l1}{l2}{l3}{l4}"
        # A stat code whose parent item isn't formed from the same L1-L4
        # would only occur if levels are malformed — covered above.
        # Check heading → chapter → section chain instead:
        if f"{l1}{l2}" not in all_heading_keys and k not in seen_orphans:
            seen_orphans.add(k)
            findings.append(Finding(
                file=filename, code=k,
                check="ORPHANED_HEADING",
                severity="ERROR",
                detail=f"Heading {l1}{l2} not found as a parent in any other row",
            ))
        if l1 not in all_chapter_keys and k not in seen_orphans:
            seen_orphans.add(k)
            findings.append(Finding(
                file=filename, code=k,
                check="ORPHANED_CHAPTER",
                severity="ERROR",
                detail=f"Chapter {l1} not found as a parent in any other row",
            ))

    return findings


def check_tariff_rates(
    rows: list[dict],
    active_item_keys: set[str],
    all_item_keys: set[str],
    formula_codes: set[str],
) -> list[Finding]:
    findings = []
    filename = "Tariff_Rates.csv"
    p = "Tdrc"

    seen: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        l1      = row.get(f"{p} Tariff Level 1", "")
        l2      = row.get(f"{p} Tariff Level 2", "")
        l3      = row.get(f"{p} Tariff Level 3", "")
        l4      = row.get(f"{p} Tariff Level 4", "")
        l5      = row.get(f"{p} Tariff Level 5", "")
        group   = row.get(f"{p} Rate Group", "")
        start   = row.get(f"{p} Start Date", "")
        expiry  = row.get(f"{p} Expiry Date", "")
        excise  = row.get(f"{p} Excise Factor", "").strip()
        formula = row.get(f"{p} Rate Formula", "").strip()

        k         = f"{l1}{l2}{l3}{l4}{l5}"
        ikey      = f"{l1}{l2}{l3}{l4}"
        dt_start  = parse_date(start)
        dt_expiry = parse_date(expiry) if not is_sentinel(expiry) else None

        # Temporal integrity
        if dt_start and dt_expiry and dt_start > dt_expiry:
            findings.append(Finding(
                file=filename, code=k,
                check="DATE_RANGE_INVERTED",
                severity="ERROR",
                detail=f"validFrom ({start.strip()}) is after validTo ({expiry.strip()})",
            ))

        # Duplicate detection — two rows are only duplicates if every
        # identifying field matches, including expiry date.
        # Same start date with different expiry dates are distinct records.
        seen[f"{k}:{group}:{excise}:{start.strip()}:{expiry.strip()}"].append(row)

        # Orphaned rates — code never existed anywhere in Tariff_Details.csv
        if ikey not in all_item_keys:
            findings.append(Finding(
                file=filename, code=k,
                check="ORPHANED_RATE",
                severity="ERROR",
                detail=f"Rate references tariff item {ikey} which does not exist "
                       f"anywhere in Tariff_Details.csv (historical or current)",
            ))
        # Zombie rates — active rate for an abolished code
        elif is_sentinel(expiry) and ikey not in active_item_keys:
            findings.append(Finding(
                file=filename, code=k,
                check="ZOMBIE_RATE",
                severity="WARNING",
                detail=f"Active rate (no expiry) references tariff item {ikey} "
                       f"which exists in Tariff_Details.csv but has no currently-"
                       f"active classification rows. The classification may have "
                       f"been abolished without cleaning up the corresponding rate.",
            ))

        # Formula reference
        if formula and formula not in formula_codes:
            findings.append(Finding(
                file=filename, code=k,
                check="UNKNOWN_FORMULA",
                severity="ERROR",
                detail=f"Rate references formula code '{formula}' which does not "
                       f"exist in Tariff_Levy_Formulas.csv",
            ))

    # Duplicates
    for sig, dupe_rows in seen.items():
        if len(dupe_rows) > 1:
            parts = sig.split(":", 4)
            k, group, excise, start, expiry = parts
            # Find differing columns to include in report
            all_cols = set(col for r in dupe_rows for col in r)
            diffs = [col for col in all_cols
                     if len(set(r.get(col,"") for r in dupe_rows)) > 1]
            findings.append(Finding(
                file=filename, code=k,
                check="DUPLICATE_RATE_ROW",
                severity="ERROR",
                detail=f"Multiple rate rows for group '{group}'"
                       f"{f' excise factor {excise}' if excise else ''} "
                       f"with identical start ({start}) and expiry ({expiry}). "
                       f"Differing columns: {diffs if diffs else 'none — rows are completely identical'}",
            ))

    return findings


def check_tariff_levies(
    rows: list[dict],
    active_item_keys: set[str],
    all_item_keys: set[str],
    formula_codes: set[str],
) -> list[Finding]:
    findings = []
    filename = "Tariff_Levies.csv"
    p = "Tlrc"

    seen: dict[str, int] = defaultdict(int)

    for row in rows:
        l1         = row.get(f"{p} Tariff Level 1", "")
        l2         = row.get(f"{p} Tariff Level 2", "")
        l3         = row.get(f"{p} Tariff Level 3", "")
        l4         = row.get(f"{p} Tariff Level 4", "")
        l5         = row.get(f"{p} Tariff Level 5", "")
        levy_type  = row.get(f"{p} Levy Type Code", "").strip()
        formula    = row.get(f"{p} Levy Formula Code", "").strip()
        start      = row.get(f"{p} Start Date", "")
        expiry     = row.get(f"{p} Expiry Date", "")

        k    = f"{l1}{l2}{l3}{l4}{l5}"
        ikey = f"{l1}{l2}{l3}{l4}"

        dt_start  = parse_date(start)
        dt_expiry = parse_date(expiry) if not is_sentinel(expiry) else None

        # Temporal integrity
        if dt_start and dt_expiry and dt_start > dt_expiry:
            findings.append(Finding(
                file=filename, code=k,
                check="DATE_RANGE_INVERTED",
                severity="ERROR",
                detail=f"validFrom ({start.strip()}) is after validTo ({expiry.strip()})",
            ))

        # Orphaned levies — code never existed anywhere in Tariff_Details.csv
        if ikey not in all_item_keys:
            findings.append(Finding(
                file=filename, code=k,
                check="ORPHANED_LEVY",
                severity="ERROR",
                detail=f"Levy references tariff item {ikey} which does not exist "
                       f"anywhere in Tariff_Details.csv (historical or current)",
            ))
        # Zombie levies — active levy for an abolished code
        elif is_sentinel(expiry) and ikey not in active_item_keys:
            findings.append(Finding(
                file=filename, code=k,
                check="ZOMBIE_LEVY",
                severity="WARNING",
                detail=f"Active levy (no expiry) references tariff item {ikey} "
                       f"which exists in Tariff_Details.csv but has no currently-"
                       f"active classification rows.",
            ))

        # Formula reference
        if formula and formula not in formula_codes:
            findings.append(Finding(
                file=filename, code=k,
                check="UNKNOWN_FORMULA",
                severity="ERROR",
                detail=f"Levy references formula code '{formula}' which does not "
                       f"exist in Tariff_Levy_Formulas.csv",
            ))

        # Duplicate
        sig = f"{k}:{levy_type}:{start.strip()}"
        seen[sig] += 1

    for sig, count in seen.items():
        if count > 1:
            k, levy_type, start = sig.split(":", 2)
            findings.append(Finding(
                file=filename, code=k,
                check="DUPLICATE_LEVY_ROW",
                severity="ERROR",
                detail=f"Multiple levy rows for type '{levy_type}' with the same "
                       f"validFrom ({start})",
            ))

    return findings


def check_levy_formulas(rows: list[dict]) -> list[Finding]:
    findings = []
    filename = "Tariff_Levy_Formulas.csv"
    seen: dict[str, int] = defaultdict(int)

    for row in rows:
        code = row.get("Lfc Levy Formula Codes", "").strip()
        rate = row.get("Lfc Levy Formula Rate", "").strip()

        if not code:
            findings.append(Finding(
                file=filename, code="",
                check="MISSING_FORMULA_CODE",
                severity="ERROR",
                detail="Row with empty formula code",
            ))
            continue

        seen[code] += 1

        # Check rate is a valid number
        try:
            float(rate)
        except ValueError:
            findings.append(Finding(
                file=filename, code=code,
                check="INVALID_FORMULA_RATE",
                severity="ERROR",
                detail=f"Formula rate '{rate}' is not a valid number",
            ))

    for code, count in seen.items():
        if count > 1:
            findings.append(Finding(
                file=filename, code=code,
                check="DUPLICATE_FORMULA_CODE",
                severity="ERROR",
                detail=f"Formula code '{code}' appears {count} times",
            ))

    return findings


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

# Severity prefixes shown inline in the detail column so the
# characterisation is visible even when the CSV is filtered or sorted.
SEVERITY_PREFIX = {
    "ERROR":   "[ERROR]",
    "WARNING": "[WARN] ",
    "INFO":    "[INFO] ",
}

def write_report(findings: list[Finding], output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "code", "check", "severity", "detail"])
        for f in sorted(findings, key=lambda x: (x.severity, x.file, x.code, x.check)):
            prefix = SEVERITY_PREFIX.get(f.severity, "")
            writer.writerow([
                f.file, f.code, f.check, f.severity,
                f"{prefix} {f.detail}",
            ])





def print_summary(findings: list[Finding]) -> None:
    from collections import Counter
    by_severity = Counter(f.severity for f in findings)
    by_check    = Counter(f.check for f in findings)

    # Map each check to its severity (take first occurrence)
    check_severity: dict[str, str] = {}
    for f in findings:
        if f.check not in check_severity:
            check_severity[f.check] = f.severity

    # Short severity labels for console display
    sev_label = {"ERROR": "ERROR", "WARNING": "WARN ", "INFO": "INFO "}

    print(f"\n  Total findings: {len(findings):,}")
    print(f"    ERROR:   {by_severity.get('ERROR', 0):,}")
    print(f"    WARNING: {by_severity.get('WARNING', 0):,}")
    print(f"    INFO:    {by_severity.get('INFO', 0):,}")
    print(f"\n  By check type:")
    for check, count in sorted(by_check.items(), key=lambda x: -x[1]):
        sev = sev_label.get(check_severity.get(check, ""), "?    ")
        print(f"    {sev}: {check:40s} {count:>6,}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def audit(input_dir: Path, output_path: Path) -> int:
    print(f"\nHS Tariff Data Quality Audit")
    print(f"Input:  {input_dir.resolve()}")
    print(f"Output: {output_path.resolve()}")

    all_findings: list[Finding] = []

    # --- Load source files ---
    print("\n--- Loading source files ---")
    file_map = {
        "details":  ("Tariff_Details.csv",       "Tic"),
        "rates":    ("Tariff_Rates.csv",          "Tdrc"),
        "levies":   ("Tariff_Levies.csv",         "Tlrc"),
        "formulas": ("Tariff_Levy_Formulas.csv",  None),
    }
    rows: dict[str, list[dict]] = {}
    for key, (filename, _) in file_map.items():
        path = input_dir / filename
        if not path.exists():
            print(f"  MISSING: {filename} — skipping")
            rows[key] = []
            continue
        rows[key] = read_csv(path)
        print(f"  Loaded {filename}: {len(rows[key]):,} rows")

    # --- Pre-build lookup sets ---
    print("\n--- Building lookup sets ---")

    # All tariff item keys from details (historical)
    all_item_keys: set[str] = set()
    active_item_keys: set[str] = set()
    for row in rows["details"]:
        l1 = row.get("Tic Tariff Level 1", "")
        l2 = row.get("Tic Tariff Level 2", "")
        l3 = row.get("Tic Tariff Level 3", "")
        l4 = row.get("Tic Tariff Level 4", "")
        ikey = f"{l1}{l2}{l3}{l4}"
        all_item_keys.add(ikey)
        if is_sentinel(row.get("Tic Expiry Date", "")):
            active_item_keys.add(ikey)

    # Formula codes
    formula_codes: set[str] = {
        row.get("Lfc Levy Formula Codes", "").strip()
        for row in rows["formulas"]
        if row.get("Lfc Levy Formula Codes", "").strip()
    }

    print(f"  All tariff item keys:    {len(all_item_keys):,}")
    print(f"  Active tariff item keys: {len(active_item_keys):,}")
    print(f"  Levy formula codes:      {len(formula_codes):,}")

    # --- Run checks ---
    print("\n--- Running checks ---")

    print("  Checking Tariff_Details.csv...", flush=True)
    findings = check_tariff_details(rows["details"])
    print(f"    {len(findings):,} findings")
    all_findings.extend(findings)

    print("  Checking Tariff_Rates.csv...", flush=True)
    findings = check_tariff_rates(
        rows["rates"], active_item_keys, all_item_keys, formula_codes
    )
    print(f"    {len(findings):,} findings")
    all_findings.extend(findings)

    print("  Checking Tariff_Levies.csv...", flush=True)
    findings = check_tariff_levies(
        rows["levies"], active_item_keys, all_item_keys, formula_codes
    )
    print(f"    {len(findings):,} findings")
    all_findings.extend(findings)

    print("  Checking Tariff_Levy_Formulas.csv...", flush=True)
    findings = check_levy_formulas(rows["formulas"])
    print(f"    {len(findings):,} findings")
    all_findings.extend(findings)

    # --- Write report ---
    print("\n--- Writing report ---")
    write_report(all_findings, output_path)
    print(f"  Written: {output_path}  ({len(all_findings):,} findings)")

    # --- Print summary ---
    print("\n--- Summary ---")
    print_summary(all_findings)

    errors = sum(1 for f in all_findings if f.severity == "ERROR")
    return errors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Data quality audit of NZ Customs tariff source CSV files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input-dir", "-i",
        default=".",
        help="Directory containing source CSV files (default: current directory)",
    )
    parser.add_argument(
        "--output", "-o",
        default="audit_report.csv",
        help="Output CSV report path (default: audit_report.csv)",
    )
    args = parser.parse_args()

    input_dir   = Path(args.input_dir)
    output_path = Path(args.output)

    if not input_dir.exists():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    error_count = audit(input_dir, output_path)
    sys.exit(0 if error_count == 0 else 1)

#EOF
