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
# HS Ontology Converter
# =====================
#
# Converts NZ Customs tariff CSV files into YAML ontology files
# compatible with the Kraken ontology importer.
# 
# Copyright notice: Source data is from NZ Customs Service.
# No known rights cover the source dataset per NZ Customs terms of use.
# 
# Classes
# -------
# HSConverter              - Base class: shared infrastructure
# HSSchemaConverter        - Generates hs.yaml (schema only)
# TariffDetailsConverter   - Generates tariff_details.yaml (hs: hierarchy instances)
# TariffRatesConverter     - Generates tariff_rates.yaml (nztar: rate instances)
# TariffLeviesConverter    - Generates tariff_levies.yaml (nztar: levy instances)
# LevyFormulasConverter    - Generates tariff_levy_formulas.yaml (nztar: formula instances)
# 
# Node Key Naming Conventions
# ---------------------------
# All node keys are XML Name compliant (no leading digits after namespace prefix).
# Numeric HS code parts are prefixed with a short alphabetic discriminator:
# 
#     hs:section.s{n}                          e.g. hs:section.s1
#     hs:chapter.c{nn}                         e.g. hs:chapter.c01
#     hs:heading.h{nnnn}                       e.g. hs:heading.h0101
#     hs:subheading.sh{nnnnnn}                 e.g. hs:subheading.sh010190
#     hs:tariffItem.ti{nnnnnnnn}               e.g. hs:tariffItem.ti01019000
#     hs:statisticalCode.sc{nnnnnnnnnn}{L}.v{date}
#                                              e.g. hs:statisticalCode.sc0101900090D.v20020101
#     nztar:rate.r{nnnnnnnnnn}.{group}.v{date} e.g. nztar:rate.r0101100011.NML.v20020101
#     nztar:levy.l{nnnnnnnnnn}.{type}.v{date}  e.g. nztar:levy.l0102210010.AS.v20120101
#     nztar:levyFormula.lf{n}                  e.g. nztar:levyFormula.lf1
# 
# Prefix legend:
#     s   section
#     c   chapter
#     h   heading
#     sh  subheading
#     ti  tariff item
#     sc  statistical code
#     r   rate
#     l   levy
#     lf  levy formula
#

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DELIMITER        = "~"
SENTINEL_EXPIRY  = "Dec 31 3000"          # NZ Customs "current, no end date"
HS_NS            = "hs"
NZTAR_NS         = "nztar"
KR_NS            = "kr"
URN_BASE         = "urn:neocortext:term"

DATE_FORMATS = [
    "%b %d %Y %I:%M%p",   # Jan  1 2002 12:00AM
    "%b  %d %Y %I:%M%p",  # Jan  1 2002 12:00AM  (double-space)
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class OntologyNode:
    """A single node in the output ontology."""
    key: str                          # e.g. hs:heading.0101.v1
    name: str                         # e.g. 0101.v1
    display: str                      # human-readable label
    description: str                  # full description text
    identity: str                     # URN
    properties: dict[str, Any] = field(default_factory=dict)
    comment: str = ""

    def to_yaml(self, indent: int = 0) -> str:
        pad = " " * indent
        lines = [f"{self.key}:"]
        lines.append(f"{pad}    name:        {_yaml_str(self.name)}")
        lines.append(f"{pad}    display:     {_yaml_str(self.display)}")
        if self.description:
            lines.append(f"{pad}    description: {_yaml_str(self.description)}")
        if self.comment:
            lines.append(f"{pad}    comment:     {_yaml_str(self.comment)}")
        lines.append(f"{pad}    identity:    {_yaml_str(self.identity)}")
        if self.properties:
            lines.append(f"{pad}    properties:")
            for k, v in self.properties.items():
                if isinstance(v, list):
                    lines.append(f"{pad}        {k}:")
                    for item in v:
                        lines.append(f"{pad}        - {item}")
                else:
                    lines.append(f"{pad}        {k}: {v}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _yaml_str(value: str) -> str:
    """Quote a string for YAML if it contains special characters."""
    if not value:
        return '""'
    needs_quoting = any(c in value for c in ':,#[]{}|>&*!\'"%@`')
    if needs_quoting:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _parse_date(raw: str) -> datetime | None:
    """Parse NZ Customs date strings into datetime objects."""
    raw = raw.strip()
    # normalise multiple spaces
    raw = re.sub(r"\s+", " ", raw)
    # strip time component for simpler parsing
    raw_date = raw.split(" 12:00")[0].split(" 11:59")[0].strip()
    for fmt in ["%b %d %Y", "%b %d %Y"]:
        try:
            return datetime.strptime(raw_date, fmt)
        except ValueError:
            pass
    return None


def _is_sentinel(raw: str) -> bool:
    """Return True if the date represents 'currently active' (Dec 31 3000)."""
    return "3000" in raw


def _is_current(expiry_raw: str) -> bool:
    """Return True if the record is currently active (sentinel expiry date)."""
    return _is_sentinel(expiry_raw)


def _format_date(dt: datetime | None) -> str:
    """Format a datetime as ISO 8601 date string."""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d")


def _make_urn(namespace: str, local: str) -> str:
    return f"{URN_BASE}:{namespace}:{local}"


# Windows-1252 smart punctuation → plain ASCII
_CP1252_MAP = {
    "\u0091": "'",
    "\u0092": "'",
    "\u0093": '"',
    "\u0094": '"',
    "\u0095": "-",
    "\u0096": "-",
    "\u0097": "--",
    "\u0085": "...",
}

def _sanitise(value: str) -> str:
    """Replace Windows-1252 smart punctuation with plain ASCII equivalents."""
    for char, replacement in _CP1252_MAP.items():
        value = value.replace(char, replacement)
    return value


def _code_key(l1: str, l2: str, l3: str, l4: str, l5: str) -> str:
    """Produce the 10-digit string key from the five level columns."""
    return f"{l1}{l2}{l3}{l4}{l5}"


def _version_suffix(start_raw: str) -> str:
    """Produce a version suffix from a start date, e.g. v20020101."""
    dt = _parse_date(start_raw)
    if dt:
        return f"v{dt.strftime('%Y%m%d')}"
    return "v0"


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class HSConverter:
    """
    Base class for all HS ontology converters.

    Subclasses implement:
        parse()   - read source CSV(s), populate self.nodes
        header()  - return the YAML file header comment block
    """

    def __init__(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
        include_history: bool = False,
    ):
        self.input_dir       = Path(input_dir)
        self.output_dir      = Path(output_dir)
        self.include_history = include_history
        self.nodes: list[OntologyNode] = []

    # ------------------------------------------------------------------
    # CSV reading
    # ------------------------------------------------------------------

    def read_csv(self, filename: str) -> list[dict[str, str]]:
        """Read a ~-delimited CSV file and return list of row dicts."""
        path = self.input_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        rows = []
        with open(path, encoding="cp1252", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=DELIMITER)
            for row in reader:
                rows.append({k.strip(): _sanitise(v.strip()) for k, v in row.items()})
        return rows

    # ------------------------------------------------------------------
    # Node factory helpers (used by subclasses)
    # ------------------------------------------------------------------

    def make_node(
        self,
        key: str,
        name: str,
        display: str,
        description: str,
        identity: str,
        properties: dict | None = None,
        comment: str = "",
    ) -> OntologyNode:
        return OntologyNode(
            key=key,
            name=name,
            display=display,
            description=description,
            identity=identity,
            properties=properties or {},
            comment=comment,
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def header(self) -> str:
        """Return the YAML file header. Subclasses override."""
        return ""

    def parse(self) -> None:
        """Populate self.nodes. Subclasses must implement."""
        raise NotImplementedError

    def render(self) -> str:
        """Render all nodes to YAML string."""
        parts = [self.header()]
        for node in self.nodes:
            parts.append(node.to_yaml())
            parts.append("")  # blank line between nodes
        return "\n".join(parts)

    def write(self, filename: str) -> Path:
        """Parse, render, and write output YAML file using streaming to limit memory use."""
        import time
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / filename

        t_start = time.time()

        self.nodes = []
        self.parse()

        node_count = len(self.nodes)
        print(f"  Writing {node_count:,} nodes...", flush=True)

        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(self.header())
            for node in self.nodes:
                fh.write(node.to_yaml())
                fh.write("\n\n")

        # Free memory
        self.nodes = []

        elapsed = time.time() - t_start
        print(f"Written: {out_path}  ({node_count:,} nodes)  [{elapsed:.1f}s]")
        return out_path


# ---------------------------------------------------------------------------
# HSSchemaConverter  →  hs.yaml
# ---------------------------------------------------------------------------

class HSSchemaConverter(HSConverter):
    """
    Generates hs.yaml: the core HS ontology schema.
    Contains:
      - ontology header
      - hs: node type declarations (section, chapter, heading, etc.)
      - hs: relation type declarations
      - hs:tradedGood root node
      - nztar: node type and relation declarations
    No instance data.
    """

    def header(self) -> str:
        return """\
# Harmonized System Ontology Schema
#
# Generated by HSSchemaConverter.
# Source: NZ Customs Service Working Tariff
# WCO Harmonized System Nomenclature (HS 2022)
#
# Namespaces:
#   hs:     WCO Harmonized System classification hierarchy (internationally portable)
#   nztar:  NZ Customs Working Tariff administrative data (NZ-specific)
#   kr:     Kraken upper ontology
#

ontology:
    version:     1.0
    id:          hs
    title:       Harmonized System Ontology
    description: "Domain ontology for the WCO Harmonized System commodity classification, grounded in the Kraken upper ontology. The hs: namespace contains the internationally standardised classification hierarchy. The nztar: namespace contains NZ Customs Working Tariff administrative data."
    author:      "NZ Customs Service / WCO"
    created:     2024-01-01
    contexts:
        hs:     $HS_TERM_NAMESPACE_URI
        nztar:  $NZTAR_TERM_NAMESPACE_URI
        kr:     $KRAKEN_TERM_NAMESPACE_URI

"""

    def parse(self) -> None:
        self.nodes = []
        self._add_root_node()
        self._add_hs_node_types()
        self._add_hs_relation_types()
        self._add_nztar_node_types()
        self._add_nztar_relation_types()

    def _add_root_node(self) -> None:
        self.nodes.append(self.make_node(
            key="hs:tradedGood",
            name="tradedGood",
            display="Traded Good",
            description="Any thing that may be the subject of international trade and therefore appear on a customs declaration, manifest, or waybill. This is the root node of the HS classification hierarchy.",
            identity=_make_urn(HS_NS, "tradedGood"),
            properties={"kr:kindOf": "kr:thing"},
        ))

    def _add_hs_node_types(self) -> None:
        types = [
            ("hs:nomenclature", "nomenclature", "Nomenclature",
             "A specific edition of the WCO Harmonized System Nomenclature."),
            ("hs:section", "section", "Section",
             "A Section of the HS Nomenclature. There are 21 Sections, each grouping related Chapters. Sections are identified by Roman numerals."),
            ("hs:chapter", "chapter", "Chapter",
             "A Chapter of the HS Nomenclature. Chapters are 2-digit groupings within a Section."),
            ("hs:heading", "heading", "Heading",
             "A Heading of the HS Nomenclature. Headings are 4-digit codes within a Chapter."),
            ("hs:subheading", "subheading", "Subheading",
             "A Subheading of the HS Nomenclature. Subheadings are 6-digit codes within a Heading. This is the limit of the internationally standardised HS code."),
            ("hs:tariffItem", "tariffItem", "Tariff Item",
             "An 8-digit NZ Customs Tariff Item, extending the international 6-digit subheading with NZ-specific classification."),
            ("hs:statisticalCode", "statisticalCode", "Statistical Code",
             "A 10-digit NZ Customs Statistical Code, the leaf node of the NZ tariff hierarchy, used for statistical reporting."),
        ]
        for key, name, display, desc in types:
            self.nodes.append(self.make_node(
                key=key,
                name=name,
                display=display,
                description=desc,
                identity=_make_urn(HS_NS, name),
                properties={"kr:kindOf": "kr:concept"},
            ))

    def _add_hs_relation_types(self) -> None:
        # Hierarchical relations — all kindOf kr:predicate.kindOf
        hier = [
            ("hs:isStatisticalCodeOf", "isStatisticalCodeOf", "Is Statistical Code Of",
             "The subject Statistical Code is a subcategory of the object Tariff Item."),
            ("hs:isTariffItemOf", "isTariffItemOf", "Is Tariff Item Of",
             "The subject Tariff Item is a subcategory of the object Subheading."),
            ("hs:isSubheadingOf", "isSubheadingOf", "Is Subheading Of",
             "The subject Subheading is a subcategory of the object Heading."),
            ("hs:isHeadingOf", "isHeadingOf", "Is Heading Of",
             "The subject Heading is a subcategory of the object Chapter."),
            ("hs:isChapterOf", "isChapterOf", "Is Chapter Of",
             "The subject Chapter is a subcategory of the object Section."),
            ("hs:isSectionOf", "isSectionOf", "Is Section Of",
             "The subject Section is a subcategory of the root traded good node."),
        ]
        for key, name, display, desc in hier:
            self.nodes.append(self.make_node(
                key=key,
                name=name,
                display=display,
                description=desc,
                identity=_make_urn(HS_NS, name),
                properties={
                    "kr:kindOf":    "kr:predicate.kindOf",
                    "isPredicate":  "true",
                    "isTransitive": "false",
                },
            ))

        # Temporal relations — kindOf kr:predicate
        temporal = [
            ("hs:isAmendedBy", "isAmendedBy", "Is Amended By",
             "The subject node has been administratively amended by the object node. Both share the same HS code key; only the description or metadata has changed. The subject validity period immediately precedes the object validity period.",
             "Administrative amendments occur when NZ Customs updates a code description without changing the underlying goods classification."),
            ("hs:isReplacedBy", "isReplacedBy", "Is Replaced By",
             "The subject node has been abolished and replaced by the object node, typically at a WCO revision boundary. The codes may differ; the goods coverage may be reorganised.",
             "Replacement relations occur at WCO HS edition boundaries (e.g. 2017 to 2022) when codes are restructured, split, or merged."),
        ]
        for key, name, display, desc, comment in temporal:
            self.nodes.append(self.make_node(
                key=key,
                name=name,
                display=display,
                description=desc,
                identity=_make_urn(HS_NS, name),
                properties={
                    "kr:kindOf":    "kr:predicate",
                    "isPredicate":  "true",
                    "isTransitive": "false",
                },
                comment=comment,
            ))

        # Cross-reference
        self.nodes.append(self.make_node(
            key="hs:hasAlternate",
            name="hasAlternate",
            display="Has Alternate",
            description="The subject Tariff Node has an alternate classification in the object Tariff Node, as indicated by the NZ Customs alternate tariff item field.",
            identity=_make_urn(HS_NS, "hasAlternate"),
            properties={
                "kr:kindOf":    "kr:predicate",
                "isPredicate":  "true",
                "isTransitive": "false",
            },
        ))

    def _add_nztar_node_types(self) -> None:
        types = [
            ("nztar:rate", "rate", "Tariff Rate",
             "A duty rate applicable to an HS tariff code within a specific validity period under the NZ Working Tariff."),
            ("nztar:levy", "levy", "Tariff Levy",
             "A levy applicable to an HS tariff code within a specific validity period under the NZ Working Tariff."),
            ("nztar:levyFormula", "levyFormula", "Levy Formula",
             "A formula used to calculate a tariff levy amount."),
        ]
        for key, name, display, desc in types:
            self.nodes.append(self.make_node(
                key=key,
                name=name,
                display=display,
                description=desc,
                identity=_make_urn(NZTAR_NS, name),
                properties={"kr:kindOf": "kr:concept"},
            ))

    def _add_nztar_relation_types(self) -> None:
        relations = [
            ("nztar:hasRate", "hasRate", "Has Rate",
             "The subject HS tariff node has the object rate applicable within a validity period."),
            ("nztar:hasLevy", "hasLevy", "Has Levy",
             "The subject HS tariff node has the object levy applicable within a validity period."),
            ("nztar:usesFormula", "usesFormula", "Uses Formula",
             "The subject rate or levy is calculated using the object levy formula."),
            ("nztar:appliesToCode", "appliesToCode", "Applies To Code",
             "The subject rate or levy applies to the object HS tariff code."),
        ]
        for key, name, display, desc in relations:
            self.nodes.append(self.make_node(
                key=key,
                name=name,
                display=display,
                description=desc,
                identity=_make_urn(NZTAR_NS, name),
                properties={
                    "kr:kindOf":    "kr:predicate",
                    "isPredicate":  "true",
                    "isTransitive": "false",
                },
            ))


# ---------------------------------------------------------------------------
# TariffDetailsConverter  →  tariff_details.yaml
# ---------------------------------------------------------------------------

class TariffDetailsConverter(HSConverter):
    """
    Generates tariff_details.yaml.
    Processes Tariff_Details.csv to produce:
      - Section nodes (derived from Tic Tariff Section column)
      - Chapter nodes  (Level 1)
      - Heading nodes  (Level 1+2)
      - Subheading nodes (Level 1+2+3)
      - Tariff Item nodes (Level 1+2+3+4)
      - Statistical Code nodes (Level 1+2+3+4+5, leaf)
    Each row becomes a versioned node. Amendment chains are detected
    and linked via hs:isAmendedBy. Temporal properties kr:validFrom
    and kr:validTo are attached to every node.
    """

    # Section descriptions per WCO (Roman numeral → description)
    SECTION_DESCRIPTIONS = {
        "1":  "Live animals; animal products",
        "2":  "Vegetable products",
        "3":  "Animal or vegetable fats and oils and their cleavage products; prepared edible fats; animal or vegetable waxes",
        "4":  "Prepared foodstuffs; beverages, spirits and vinegar; tobacco and manufactured tobacco substitutes",
        "5":  "Mineral products",
        "6":  "Products of the chemical or allied industries",
        "7":  "Plastics and articles thereof; rubber and articles thereof",
        "8":  "Raw hides and skins, leather, furskins and articles thereof; saddlery and harness; travel goods, handbags and similar containers; articles of animal gut",
        "9":  "Wood and articles of wood; wood charcoal; cork and articles of cork; manufactures of straw, of esparto or of other plaiting materials; basketware and wickerwork",
        "10": "Pulp of wood or of other fibrous cellulosic material; recovered (waste and scrap) paper or paperboard; paper, paperboard and articles thereof",
        "11": "Textiles and textile articles",
        "12": "Footwear, headgear, umbrellas, sun umbrellas, walking sticks, seat-sticks, whips, riding-crops and parts thereof; prepared feathers and articles made therewith; artificial flowers; articles of human hair",
        "13": "Articles of stone, plaster, cement, asbestos, mica or similar materials; ceramic products; glass and glassware",
        "14": "Natural or cultured pearls, precious or semi-precious stones, precious metals, metals clad with precious metal and articles thereof; imitation jewellery; coin",
        "15": "Base metals and articles of base metal",
        "16": "Machinery and mechanical appliances; electrical equipment; parts thereof; sound recorders and reproducers, television image and sound recorders and reproducers, and parts and accessories of such articles",
        "17": "Vehicles, aircraft, vessels and associated transport equipment",
        "18": "Optical, photographic, cinematographic, measuring, checking, precision, medical or surgical instruments and apparatus; clocks and watches; musical instruments; parts and accessories thereof",
        "19": "Arms and ammunition; parts and accessories thereof",
        "20": "Miscellaneous manufactured articles",
        "21": "Works of art, collectors' pieces and antiques",
    }

    def header(self) -> str:
        return """\
# HS Tariff Details — Instance Data
#
# Generated by TariffDetailsConverter.
# Source: NZ Customs Service — Tariff_Details.csv
# Namespace: hs:
#
# Each node represents one versioned row from the source data.
# Nodes at the same code with consecutive validity periods are linked
# via hs:isAmendedBy. The last (or only) version of a currently-active
# code has kr:validTo of 9999-12-31.
#

"""

    def parse(self) -> None:
        print("  Reading CSV...", flush=True)
        rows = self.read_csv("Tariff_Details.csv")
        print(f"  {len(rows):,} rows read. Grouping...", flush=True)
        self.nodes = []

        # O(1) node lookup by key — avoids O(n²) linear scan
        node_index: dict[str, OntologyNode] = {}

        def add_node(node: OntologyNode) -> None:
            self.nodes.append(node)
            node_index[node.key] = node

        # Track seen structural nodes to avoid duplicates
        seen_sections:    set[str] = set()
        seen_chapters:    set[str] = set()
        seen_headings:    set[str] = set()
        seen_subheadings: set[str] = set()
        seen_items:       set[str] = set()

        # Group all rows by code key (L1+L2+L3+L4+L5+Letter)
        from collections import defaultdict
        code_groups: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            key = _code_key(
                row.get("Tic Tariff Level 1", ""),
                row.get("Tic Tariff Level 2", ""),
                row.get("Tic Tariff Level 3", ""),
                row.get("Tic Tariff Level 4", ""),
                row.get("Tic Tariff Level 5", ""),
            ) + row.get("Tic Tariff Letter", "")
            code_groups[key].append(row)

        # Sort each group by start date
        for key in code_groups:
            code_groups[key].sort(
                key=lambda r: _parse_date(r.get("Tic Start Date", "")) or datetime.min
            )

        # Filter to current codes unless --include-history
        if not self.include_history:
            code_groups = {
                k: v for k, v in code_groups.items()
                if any(_is_current(r.get("Tic Expiry Date", "")) for r in v)
            }
            print(f"  (history excluded: {len(code_groups):,} current code groups remain)", flush=True)

        total = len(code_groups)
        print(f"  {total:,} code groups to process...", flush=True)
        for i, (code_key_letter, group_rows) in enumerate(sorted(code_groups.items())):
            if i % 1000 == 0 and i > 0:
                print(f"  {i:,}/{total:,} groups processed...", flush=True)

            l1     = group_rows[0].get("Tic Tariff Level 1", "")
            l2     = group_rows[0].get("Tic Tariff Level 2", "")
            l3     = group_rows[0].get("Tic Tariff Level 3", "")
            l4     = group_rows[0].get("Tic Tariff Level 4", "")
            l5     = group_rows[0].get("Tic Tariff Level 5", "")
            sec    = group_rows[0].get("Tic Tariff Section", "")

            # Structural nodes — emitted once per unique code
            if sec and sec not in seen_sections:
                seen_sections.add(sec)
                add_node(self._make_section_node(sec))

            if l1 not in seen_chapters:
                seen_chapters.add(l1)
                add_node(self._make_chapter_node(l1, sec))

            heading_code = f"{l1}{l2}"
            if heading_code not in seen_headings:
                seen_headings.add(heading_code)
                add_node(self._make_heading_node(l1, l2))

            subheading_code = f"{l1}{l2}{l3}"
            if subheading_code not in seen_subheadings:
                seen_subheadings.add(subheading_code)
                add_node(self._make_subheading_node(l1, l2, l3))

            item_code = f"{l1}{l2}{l3}{l4}"
            if item_code not in seen_items:
                seen_items.add(item_code)
                add_node(self._make_tariff_item_node(l1, l2, l3, l4))

            # When not including history, emit only the current row(s).
            # When including history, emit all versions and link amendment chain.
            if not self.include_history:
                active_rows = [r for r in group_rows if _is_current(r.get("Tic Expiry Date", ""))]
                for row in active_rows:
                    self._make_stat_code_node(row, node_index, add_node)
            else:
                version_keys = []
                for row in group_rows:
                    vkey = self._make_stat_code_node(row, node_index, add_node)
                    version_keys.append(vkey)
                # Link amendment chain using O(1) dict lookup
                for j in range(len(version_keys) - 1):
                    node = node_index.get(version_keys[j])
                    if node:
                        node.properties["hs:isAmendedBy"] = version_keys[j + 1]

    # ------------------------------------------------------------------
    # Node builders
    # ------------------------------------------------------------------

    def _make_section_node(self, sec: str) -> OntologyNode:
        roman = self._to_roman(int(sec))
        desc  = self.SECTION_DESCRIPTIONS.get(sec, f"Section {roman}")
        key   = f"hs:section.s{sec}"
        return self.make_node(
            key=key,
            name=f"section.{sec}",
            display=f"Section {roman}",
            description=desc,
            identity=_make_urn(HS_NS, f"section.{sec}"),
            properties={
                "kr:instanceOf": "hs:section",
                "hs:isSectionOf": "hs:tradedGood",
            },
        )

    def _make_chapter_node(self, l1: str, sec: str) -> OntologyNode:
        key = f"hs:chapter.c{l1}"
        return self.make_node(
            key=key,
            name=f"chapter.{l1}",
            display=f"Chapter {l1}",
            description=f"HS Chapter {l1}.",
            identity=_make_urn(HS_NS, f"chapter.{l1}"),
            properties={
                "kr:instanceOf":  "hs:chapter",
                "hs:isChapterOf": f"hs:section.s{sec}",
            },
        )

    def _make_heading_node(self, l1: str, l2: str) -> OntologyNode:
        code = f"{l1}{l2}"
        key  = f"hs:heading.h{code}"
        return self.make_node(
            key=key,
            name=f"heading.{code}",
            display=f"Heading {code}",
            description=f"HS Heading {code}.",
            identity=_make_urn(HS_NS, f"heading.{code}"),
            properties={
                "kr:instanceOf": "hs:heading",
                "hs:isHeadingOf": f"hs:chapter.c{l1}",
            },
        )

    def _make_subheading_node(self, l1: str, l2: str, l3: str) -> OntologyNode:
        code = f"{l1}{l2}{l3}"
        key  = f"hs:subheading.sh{code}"
        return self.make_node(
            key=key,
            name=f"subheading.{code}",
            display=f"Subheading {code}",
            description=f"HS Subheading {code}.",
            identity=_make_urn(HS_NS, f"subheading.{code}"),
            properties={
                "kr:instanceOf":    "hs:subheading",
                "hs:isSubheadingOf": f"hs:heading.h{l1}{l2}",
            },
        )

    def _make_tariff_item_node(self, l1: str, l2: str, l3: str, l4: str) -> OntologyNode:
        code = f"{l1}{l2}{l3}{l4}"
        key  = f"hs:tariffItem.ti{code}"
        return self.make_node(
            key=key,
            name=f"tariffItem.{code}",
            display=f"Tariff Item {code}",
            description=f"NZ Tariff Item {code}.",
            identity=_make_urn(HS_NS, f"tariffItem.{code}"),
            properties={
                "kr:instanceOf":  "hs:tariffItem",
                "hs:isTariffItemOf": f"hs:subheading.sh{l1}{l2}{l3}",
            },
        )

    def _make_stat_code_node(
        self, row: dict, node_index: dict, add_node
    ) -> str:
        l1     = row.get("Tic Tariff Level 1", "")
        l2     = row.get("Tic Tariff Level 2", "")
        l3     = row.get("Tic Tariff Level 3", "")
        l4     = row.get("Tic Tariff Level 4", "")
        l5     = row.get("Tic Tariff Level 5", "")
        letter = row.get("Tic Tariff Letter", "")
        desc   = row.get("Tic Tariff Description", "")
        start  = row.get("Tic Start Date", "")
        expiry = row.get("Tic Expiry Date", "")
        alt    = row.get("Tic Alternate Tariff Item", "").strip()
        unit   = row.get("Tic Statistical Unit", "").strip()
        sup    = row.get("Tic Supplementary Unit", "").strip()

        code    = f"{l1}{l2}{l3}{l4}{l5}"
        vsuffix = _version_suffix(start)
        key     = f"hs:statisticalCode.sc{code}{letter}.{vsuffix}"
        name    = f"statisticalCode.{code}{letter}.{vsuffix}"

        valid_from = _format_date(_parse_date(start))
        valid_to   = "9999-12-31" if _is_sentinel(expiry) else _format_date(_parse_date(expiry))

        props: dict[str, Any] = {
            "kr:instanceOf":          "hs:statisticalCode",
            "hs:isStatisticalCodeOf": f"hs:tariffItem.ti{l1}{l2}{l3}{l4}",
            "kr:validFrom":           valid_from,
            "kr:validTo":             valid_to,
        }
        if unit:
            props["hs:statisticalUnit"] = unit
        if sup:
            props["hs:supplementaryUnit"] = sup
        if alt:
            props["hs:hasAlternate"] = f"hs:statisticalCode.{alt}"

        display = f"{code}{letter}: {desc}" if desc else f"{code}{letter}"

        add_node(self.make_node(
            key=key,
            name=name,
            display=display,
            description=desc,
            identity=_make_urn(HS_NS, name),
            properties=props,
        ))
        return key

    @staticmethod
    def _to_roman(n: int) -> str:
        vals = [
            (1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),
            (100,"C"),(90,"XC"),(50,"L"),(40,"XL"),
            (10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")
        ]
        result = ""
        for v, s in vals:
            while n >= v:
                result += s
                n -= v
        return result


# ---------------------------------------------------------------------------
# TariffRatesConverter  →  tariff_rates.yaml
# ---------------------------------------------------------------------------

class TariffRatesConverter(HSConverter):
    """
    Generates tariff_rates.yaml.
    Processes Tariff_Rates.csv to produce nztar:rate nodes,
    each linked to its corresponding hs:statisticalCode node.
    """

    def header(self) -> str:
        return """\
# NZ Tariff Rates — Instance Data
#
# Generated by TariffRatesConverter.
# Source: NZ Customs Service — Tariff_Rates.csv
# Namespace: nztar:
#
# Each node represents one versioned rate row from the source data.
# Rates are linked to their corresponding hs: statistical code nodes
# via nztar:appliesToCode.
#

"""

    def _current_tariff_item_keys(self) -> set[str]:
        """Build the set of currently-active tariff item keys from Tariff_Details.csv.
        Used to skip rate rows whose classification code has expired."""
        print("  Pre-scanning Tariff_Details.csv for active tariff items...", flush=True)
        rows = self.read_csv("Tariff_Details.csv")
        keys = set()
        for row in rows:
            expiry = row.get("Tic Expiry Date", "")
            if not self.include_history and not _is_current(expiry):
                continue
            l1 = row.get("Tic Tariff Level 1", "")
            l2 = row.get("Tic Tariff Level 2", "")
            l3 = row.get("Tic Tariff Level 3", "")
            l4 = row.get("Tic Tariff Level 4", "")
            keys.add(f"hs:tariffItem.ti{l1}{l2}{l3}{l4}")
        print(f"  {len(keys):,} active tariff item keys found.", flush=True)
        return keys

    def parse(self) -> None:
        valid_items = self._current_tariff_item_keys()
        rows = self.read_csv("Tariff_Rates.csv")
        self.nodes = []
        seen: set[str] = set()
        total = len(rows)
        skipped = 0
        print(f"  {total:,} rate rows to process...", flush=True)

        for i, row in enumerate(rows):
            if i % 10000 == 0 and i > 0:
                print(f"  {i:,}/{total:,}...", flush=True)
            if not self.include_history and not _is_current(row.get("Tdrc Expiry Date", "")):
                continue
            l1      = row.get("Tdrc Tariff Level 1", "")
            l2      = row.get("Tdrc Tariff Level 2", "")
            l3      = row.get("Tdrc Tariff Level 3", "")
            l4      = row.get("Tdrc Tariff Level 4", "")
            l5      = row.get("Tdrc Tariff Level 5", "")
            group   = row.get("Tdrc Rate Group", "")
            start   = row.get("Tdrc Start Date", "")
            expiry  = row.get("Tdrc Expiry Date", "")
            formula = row.get("Tdrc Rate Formula", "").strip()
            fa      = row.get("Tdrc Factor A", "").strip()
            fb      = row.get("Tdrc Factor B", "").strip()
            fc      = row.get("Tdrc Factor C", "").strip()
            fd      = row.get("Tdrc Factor D", "").strip()
            fe      = row.get("Tdrc Factor E", "").strip()
            ff      = row.get("Tdrc Factor F", "").strip()

            code    = _code_key(l1, l2, l3, l4, l5)
            vsuffix = _version_suffix(start)
            key     = f"nztar:rate.r{code}.{group}.{vsuffix}"

            if key in seen:
                continue
            seen.add(key)

            valid_from = _format_date(_parse_date(start))
            valid_to   = "9999-12-31" if _is_sentinel(expiry) else _format_date(_parse_date(expiry))

            # Rates apply at the tariff item level (L1+L2+L3+L4);
            # the letter variant is not present in the rates file.
            item_code = f"{l1}{l2}{l3}{l4}"
            item_key  = f"hs:tariffItem.ti{item_code}"
            if item_key not in valid_items:
                skipped += 1
                continue
            props: dict[str, Any] = {
                "kr:instanceOf":         "nztar:rate",
                "nztar:appliesToCode":   f"hs:tariffItem.ti{item_code}",
                "nztar:rateGroup":       group,
                "kr:validFrom":          valid_from,
                "kr:validTo":            valid_to,
            }
            if formula:
                props["nztar:usesFormula"] = f"nztar:levyFormula.lf{formula}"
            for label, val in [
                ("nztar:factorA", fa), ("nztar:factorB", fb),
                ("nztar:factorC", fc), ("nztar:factorD", fd),
                ("nztar:factorE", fe), ("nztar:factorF", ff),
            ]:
                if val:
                    props[label] = val

            self.nodes.append(self.make_node(
                key=key,
                name=f"rate.{code}.{group}.{vsuffix}",
                display=f"Rate {code} {group} {valid_from}",
                description=f"NZ Working Tariff duty rate for code {code}, rate group {group}, valid from {valid_from}.",
                identity=_make_urn(NZTAR_NS, f"rate.r{code}.{group}.{vsuffix}"),
                properties=props,
            ))

        if skipped:
            print(
                f"  NOTE: Skipped {skipped:,} rate rows referencing tariff items with no "
                f"currently-active classification in Tariff_Details.csv.\n"
                f"  These are likely zombie entries — rates whose classification codes have "
                f"been abolished but whose rate rows were not cleaned up in the source data.\n"
                f"  This appears to be a data quality issue in the NZ Customs source dataset.",
                flush=True,
            )


# ---------------------------------------------------------------------------
# TariffLeviesConverter  →  tariff_levies.yaml
# ---------------------------------------------------------------------------

class TariffLeviesConverter(HSConverter):
    """
    Generates tariff_levies.yaml.
    Processes Tariff_Levies.csv to produce nztar:levy nodes.
    """

    def header(self) -> str:
        return """\
# NZ Tariff Levies — Instance Data
#
# Generated by TariffLeviesConverter.
# Source: NZ Customs Service — Tariff_Levies.csv
# Namespace: nztar:
#

"""

    def parse(self) -> None:
        rows = self.read_csv("Tariff_Levies.csv")
        self.nodes = []
        seen: set[str] = set()
        total = len(rows)
        print(f"  {total:,} rows to process...", flush=True)

        for i, row in enumerate(rows):
            if i % 5000 == 0 and i > 0:
                print(f"  {i:,}/{total:,}...", flush=True)
            if not self.include_history and not _is_current(row.get("Tlrc Expiry Date", "")):
                continue
            l1         = row.get("Tlrc Tariff Level 1", "")
            l2         = row.get("Tlrc Tariff Level 2", "")
            l3         = row.get("Tlrc Tariff Level 3", "")
            l4         = row.get("Tlrc Tariff Level 4", "")
            l5         = row.get("Tlrc Tariff Level 5", "")
            levy_type  = row.get("Tlrc Levy Type Code", "").strip()
            formula    = row.get("Tlrc Levy Formula Code", "").strip()
            start      = row.get("Tlrc Start Date", "")
            expiry     = row.get("Tlrc Expiry Date", "")

            code    = _code_key(l1, l2, l3, l4, l5)
            vsuffix = _version_suffix(start)
            key     = f"nztar:levy.l{code}.{levy_type}.{vsuffix}"

            if key in seen:
                continue
            seen.add(key)

            valid_from = _format_date(_parse_date(start))
            valid_to   = "9999-12-31" if _is_sentinel(expiry) else _format_date(_parse_date(expiry))

            item_code = f"{l1}{l2}{l3}{l4}"
            props: dict[str, Any] = {
                "kr:instanceOf":       "nztar:levy",
                "nztar:appliesToCode": f"hs:tariffItem.ti{item_code}",
                "nztar:levyTypeCode":  levy_type,
                "kr:validFrom":        valid_from,
                "kr:validTo":          valid_to,
            }
            if formula:
                props["nztar:usesFormula"] = f"nztar:levyFormula.lf{formula}"

            self.nodes.append(self.make_node(
                key=key,
                name=f"levy.{code}.{levy_type}.{vsuffix}",
                display=f"Levy {code} {levy_type} {valid_from}",
                description=f"NZ Working Tariff levy for code {code}, levy type {levy_type}, valid from {valid_from}.",
                identity=_make_urn(NZTAR_NS, f"levy.{code}.{levy_type}.{vsuffix}"),
                properties=props,
            ))


# ---------------------------------------------------------------------------
# LevyFormulasConverter  →  tariff_levy_formulas.yaml
# ---------------------------------------------------------------------------

class LevyFormulasConverter(HSConverter):
    """
    Generates tariff_levy_formulas.yaml.
    Processes Tariff_Levy_Formulas.csv to produce nztar:levyFormula nodes.
    """

    def header(self) -> str:
        return """\
# NZ Levy Formulas — Instance Data
#
# Generated by LevyFormulasConverter.
# Source: NZ Customs Service — Tariff_Levy_Formulas.csv
# Namespace: nztar:
#

"""

    def parse(self) -> None:
        rows = self.read_csv("Tariff_Levy_Formulas.csv")
        self.nodes = []

        for row in rows:
            code = row.get("Lfc Levy Formula Codes", "").strip()
            rate = row.get("Lfc Levy Formula Rate", "").strip()

            if not code:
                continue

            key = f"nztar:levyFormula.lf{code}"
            self.nodes.append(self.make_node(
                key=key,
                name=f"levyFormula.{code}",
                display=f"Levy Formula {code}",
                description=f"NZ Customs levy calculation formula {code} with rate factor {rate}.",
                identity=_make_urn(NZTAR_NS, f"levyFormula.{code}"),
                properties={
                    "kr:instanceOf":     "nztar:levyFormula",
                    "nztar:formulaCode": code,
                    "nztar:formulaRate": rate,
                },
            ))

#EOF
