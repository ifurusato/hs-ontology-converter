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
# convert.py — CLI entry point for the HS ontology converter.
# 
# Usage examples
# --------------
# Convert everything (parallel):
#     python convert.py --all --input-dir ./data --output-dir ./ontology
# 
# Convert just the schema and hierarchy:
#     python convert.py --schema --tariff-details --input-dir ./data --output-dir ./ontology
# 
# Convert a single file:
#     python convert.py --tariff-rates --input-dir ./data --output-dir ./ontology
#

import argparse
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from hs_converter import (
    HSSchemaConverter,
    TariffDetailsConverter,
    TariffRatesConverter,
    TariffLeviesConverter,
    LevyFormulasConverter,
)

# Must be module-level for multiprocessing pickling
def _run_converter(args: tuple) -> tuple[str, str | None]:
    """Worker function: instantiate and run a single converter."""
    cls_name, filename, input_dir, output_dir, include_history = args

    # Re-import in worker process
    import hs_converter as hc
    cls = getattr(hc, cls_name)

    print(f"--- {filename} ---", flush=True)
    try:
        converter = cls(input_dir=input_dir, output_dir=output_dir,
                        include_history=include_history)
        converter.write(filename)
        return filename, None
    except FileNotFoundError as e:
        return filename, f"Skipped: {e}"
    except Exception as e:
        import traceback
        return filename, f"Error: {e}\n{traceback.format_exc()}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert NZ Customs tariff CSV files to Kraken ontology YAML.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input-dir", "-i",
        default=".",
        help="Directory containing the source CSV files (default: current directory)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./ontology",
        help="Directory for output YAML files (default: ./ontology)",
    )
    parser.add_argument("--all",            action="store_true", help="Run all converters")
    parser.add_argument("--schema",         action="store_true", help="Generate hs.yaml (schema)")
    parser.add_argument("--tariff-details", action="store_true", help="Generate tariff_details.yaml")
    parser.add_argument("--tariff-rates",   action="store_true", help="Generate tariff_rates.yaml")
    parser.add_argument("--tariff-levies",  action="store_true", help="Generate tariff_levies.yaml")
    parser.add_argument("--levy-formulas",  action="store_true", help="Generate tariff_levy_formulas.yaml")
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=0,
        help="Number of parallel workers (default: one per converter, up to CPU count)",
    )
    parser.add_argument(
        "--include-history",
        action="store_true",
        default=False,
        help="Include all historical (expired) records. Default: current records only.",
    )

    args = parser.parse_args()

    run_all = args.all or not any([
        args.schema, args.tariff_details, args.tariff_rates,
        args.tariff_levies, args.levy_formulas,
    ])

    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    # (class_name, output_filename) — class name used for pickling
    converters = []
    if run_all or args.schema:
        converters.append(("HSSchemaConverter",      "hs.yaml"))
    if run_all or args.tariff_details:
        converters.append(("TariffDetailsConverter", "tariff_details.yaml"))
    if run_all or args.levy_formulas:
        converters.append(("LevyFormulasConverter",  "tariff_levy_formulas.yaml"))
    if run_all or args.tariff_rates:
        converters.append(("TariffRatesConverter",   "tariff_rates.yaml"))
    if run_all or args.tariff_levies:
        converters.append(("TariffLeviesConverter",  "tariff_levies.yaml"))

    output_dir.mkdir(parents=True, exist_ok=True)

    import time
    t_pipeline = time.time()

    if len(converters) == 1:
        # Single converter — run in-process
        cls_name, filename = converters[0]
        print(f"\n--- {filename} ---")
        result_file, error = _run_converter(
            (cls_name, filename, str(input_dir), str(output_dir), args.include_history)
        )
        if error:
            print(f"  {error}", file=sys.stderr)
    else:
        # Multiple converters — run in parallel
        n_workers = args.workers or min(len(converters), multiprocessing.cpu_count())
        print(f"\nRunning {len(converters)} converters in parallel ({n_workers} workers)...")

        tasks = [
            (cls_name, filename, str(input_dir), str(output_dir), args.include_history)
            for cls_name, filename in converters
        ]

        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {executor.submit(_run_converter, task): task[1]
                       for task in tasks}
            for future in as_completed(futures):
                filename, error = future.result()
                if error:
                    print(f"  {filename}: {error}", file=sys.stderr)

    elapsed = time.time() - t_pipeline
    mins, secs = divmod(elapsed, 60)
    print(f"\nDone.  Total elapsed: {int(mins)}m {secs:.1f}s")


if __name__ == "__main__":
    main()

#EOF
