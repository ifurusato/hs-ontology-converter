HS Ontology Converter
=====================

A Python tool that converts the `New Zealand Customs Service Working Tariff`_
CSV data files into structured YAML ontology files compatible with the
Kraken knowledge representation system.

The converter maps the WCO Harmonized System (HS) commodity classification
hierarchy into a domain ontology grounded in the Kraken upper ontology
(``kr:`` namespace), producing a set of interlinked YAML files that can be
loaded into any application supporting the Kraken ontology format. The Kraken
ontology is a private system; the ``kr:`` namespace references in the output
are symbolic identifiers intended for use with that system.


Background
----------

The `Harmonized Commodity Description and Coding System`_ (HS) is an
international nomenclature developed by the `World Customs Organization`_
(WCO) for the classification of goods in international trade. It is used
by more than 200 countries and covers approximately 98% of world trade.
The system is revised approximately every five years; the current edition
is HS 2022 (7th edition).

New Zealand Customs uses the WCO HS as the basis for its Working Tariff,
extending the international 6-digit subheadings to 8- and 10-digit codes
for NZ-specific tariff items and statistical reporting. The first 6 digits
of any NZ tariff code are identical to the corresponding WCO HS subheading,
making the NZ dataset internationally interoperable.

NZ Customs publishes its tariff data freely with no known rights restrictions,
updated daily.


Ontology Design
---------------

The converter produces two namespaces:

``hs:``
    The internationally portable WCO classification hierarchy. Contains
    the full tree from the root ``hs:tradedGood`` node down through Sections,
    Chapters, Headings, Subheadings, Tariff Items, and Statistical Codes.
    Grounded in the ``kr:`` upper ontology. Reusable independently of NZ.

``nztar:``
    NZ Customs Working Tariff administrative data. Contains duty rates,
    levies, and levy formulas specific to New Zealand. References ``hs:``
    nodes via ``nztar:appliesToCode`` relations.

Hierarchy
~~~~~~~~~

The HS classification hierarchy is modelled using semantically precise
level-specific relation types, each a specialisation of ``kr:predicate.kindOf``
and therefore traversable via the upper ontology::

    hs:tradedGood               (root — "any internationally traded good")
      └── hs:section            hs:isSectionOf
            └── hs:chapter      hs:isChapterOf
                  └── hs:heading        hs:isHeadingOf
                        └── hs:subheading     hs:isSubheadingOf
                              └── hs:tariffItem       hs:isTariffItemOf
                                    └── hs:statisticalCode  hs:isStatisticalCodeOf

Temporal Versioning
~~~~~~~~~~~~~~~~~~~

Each row in the source CSV becomes a distinct versioned graph node carrying
``kr:validFrom`` and ``kr:validTo`` properties. Consecutive versions of the
same code are linked via ``hs:isAmendedBy``. Codes abolished at WCO revision
boundaries may be linked to their successors via ``hs:isReplacedBy``.

By default the converter emits only currently-active nodes (those with a
sentinel expiry date of ``Dec 31 3000``). The full historical record,
including all amendment chains back to 1988, is available via the
``--include-history`` flag.

XML Name Compliance
~~~~~~~~~~~~~~~~~~~

All node keys are XML Name compliant — no local part begins with a digit.
Numeric HS code segments are prefixed with a short alphabetic discriminator:

=============================  ======  ====================================
Node type                      Prefix  Example
=============================  ======  ====================================
Section                        ``s``   ``hs:section.s1``
Chapter                        ``c``   ``hs:chapter.c01``
Heading                        ``h``   ``hs:heading.h0101``
Subheading                     ``sh``  ``hs:subheading.sh010190``
Tariff Item                    ``ti``  ``hs:tariffItem.ti01019000``
Statistical Code               ``sc``  ``hs:statisticalCode.sc0101900090D.v20020101``
Rate                           ``r``   ``nztar:rate.r0101100011.NML.v20020101``
Levy                           ``l``   ``nztar:levy.l0102210010.AS.v20120101``
Levy Formula                   ``lf``  ``nztar:levyFormula.lf1``
=============================  ======  ====================================


Source Data
-----------

The source CSV files are published freely by NZ Customs Service and are
updated every 24 hours. There are no known rights covering this dataset.

Download page:
    https://www.customs.govt.nz/business/tariffs/tariff-classifications-and-rates/

Direct downloads:

- `Tariff data (tar.gz) <https://www.customs.govt.nz/media/0nmaamqd/tarifftar.gz>`_
- `Concession data (tar.gz) <https://www.customs.govt.nz/media/iw5gqprj/concessiontar.gz>`_
- `Readme (PDF) <https://www.customs.govt.nz/media/y1dmuyec/tariff-and-concession-readme.pdf>`_

The tariff archive extracts to the following CSV files (``~``-delimited,
Windows-1252 encoded):

=================================  ============  =========================================
File                               Used          Description
=================================  ============  =========================================
``Tariff_Details.csv``             Yes           Classification hierarchy, descriptions,
                                                 validity periods
``Tariff_Rates.csv``               Yes           Duty rates per tariff code
``Tariff_Levies.csv``              Yes           Levies per tariff code
``Tariff_Levy_Formulas.csv``       Yes           Levy calculation formula lookup table
``Concession_Details.csv``         No            NZ-specific importer concessions
``Concession_Rates.csv``           No            Concession duty rates
``Concession_to_Tariff.csv``       No            Concession-to-code mapping table
=================================  ============  =========================================

The concession files are not processed; they contain NZ Customs
administrative grant data that belongs in a separate ``nz:`` domain ontology
rather than the internationally portable ``hs:`` classification hierarchy.


Output Files
------------

Running the converter produces five YAML files:

=================================  =========  ========================================
File                               Namespace  Contents
=================================  =========  ========================================
``hs.yaml``                        ``hs:``    Ontology schema: relation type and node
                                              type declarations, root node
``tariff_details.yaml``            ``hs:``    Classification hierarchy instances
``tariff_levy_formulas.yaml``      ``nztar:`` Levy formula lookup nodes
``tariff_rates.yaml``              ``nztar:`` Duty rate nodes
``tariff_levies.yaml``             ``nztar:`` Levy nodes
=================================  =========  ========================================

Approximate sizes (current-only mode, as of March 2026):

- ``hs.yaml`` — 9 KB (24 schema nodes)
- ``tariff_details.yaml`` — 13 MB (32,546 nodes)
- ``tariff_levies.yaml`` — 420 KB (775 nodes)
- ``tariff_levy_formulas.yaml`` — 207 KB (586 nodes)
- ``tariff_rates.yaml`` — 78 MB (142,994 nodes)


Setup
-----

1. Clone the repository::

    git clone https://github.com/<your-username>/hs-ontology-converter.git
    cd hs-ontology-converter

2. Download the NZ Customs tariff data::

    wget https://www.customs.govt.nz/media/0nmaamqd/tarifftar.gz
    tar -xzf tarifftar.gz

3. Move the four required CSV files into the ``data/`` directory::

    mkdir -p data
    mv Tariff_Details.csv Tariff_Rates.csv Tariff_Levies.csv Tariff_Levy_Formulas.csv data/

   The ``data/`` directory is listed in ``.gitignore`` and will not be
   committed to the repository. The source data must be downloaded
   separately from NZ Customs Service as described above.

4. Install PyYAML (required for ``validate.py``)::

    sudo apt install python3-yaml
    # or
    pip install pyyaml

5. Run the pipeline::

    chmod +x run_all.sh
    ./run_all.sh


Requirements
------------

- Python 3.10 or later
- PyYAML (for ``validate.py`` only)::

    sudo apt install python3-yaml
    # or
    pip install pyyaml


Usage
-----

Download and extract the NZ Customs tariff archive::

    wget https://www.customs.govt.nz/media/0nmaamqd/tarifftar.gz
    tar -xzf tarifftar.gz

Convert current codes only (recommended default)::

    python convert.py --all --input-dir ./data --output-dir ./ontology

Convert full historical record (includes all versions since 1988)::

    python convert.py --all --include-history --input-dir ./data --output-dir ./ontology_history

Convert a single file::

    python convert.py --tariff-details --input-dir ./data --output-dir ./ontology

All options::

    python convert.py --help

Validate output::

    python validate.py                      # default ./ontology
    python validate.py ./ontology           # current-only run
    python validate.py ./ontology_history   # historical run


CLI Reference
-------------

``convert.py``
~~~~~~~~~~~~~~

.. code-block:: text

    usage: convert.py [-h] [--input-dir DIR] [--output-dir DIR]
                      [--all] [--schema] [--tariff-details]
                      [--tariff-rates] [--tariff-levies]
                      [--levy-formulas] [--include-history]
                      [--workers N]

    --all               Run all converters (default if no file flag given)
    --schema            Generate hs.yaml (schema only)
    --tariff-details    Generate tariff_details.yaml
    --tariff-rates      Generate tariff_rates.yaml
    --tariff-levies     Generate tariff_levies.yaml
    --levy-formulas     Generate tariff_levy_formulas.yaml
    --include-history   Include all historical (expired) records
    --workers N         Number of parallel workers (default: one per converter)
    --input-dir DIR     Source CSV directory (default: current directory)
    --output-dir DIR    Output YAML directory (default: ./ontology)

``validate.py``
~~~~~~~~~~~~~~~

.. code-block:: text

    usage: validate.py [ontology_dir]

    Checks performed:
      - File existence and sizes
      - YAML parseability
      - Node counts by namespace
      - XML Name compliance
      - Schema completeness (all expected types and relations present)
      - Hierarchy structure and node counts per level
      - HS section and chapter count sanity bounds
      - Amendment chain integrity (history mode)
      - Cross-file reference resolution (rates/levies → details, formulas)

    Exit codes: 0 = all checks passed, 1 = errors found


Data Quality Notes
------------------

During development, an audit of the source data revealed that 348 tariff
items in ``Tariff_Rates.csv`` carry active rate entries (sentinel expiry
``Dec 31 3000``) for classification codes that have no currently-active
rows in ``Tariff_Details.csv``. These are believed to be zombie entries —
rates whose corresponding classification codes were abolished at a WCO
revision boundary but whose rate rows were not cleaned up in the NZ Customs
source dataset. The converter skips these rows and reports them; the
validator lists them as a named warning rather than an error.


``run_all.sh``
~~~~~~~~~~~~~

Runs the complete pipeline in order — current ontology, historical ontology,
both validations, and the audit — with preflight checks and a final summary
of all output files and their sizes::

    ./run_all.sh                            # CSVs in current directory
    ./run_all.sh --input-dir /path/to/csvs  # CSVs elsewhere
    ./run_all.sh --python python3.11        # specific Python executable

This is the recommended entry point for anyone wishing to reproduce the
full output from scratch, including NZ Customs if they wish to verify the
audit findings independently.

``audit.py``
~~~~~~~~~~~~

.. code-block:: text

    usage: audit.py [-h] [--input-dir DIR] [--output FILE]

    Checks all four source CSV files for data anomalies and writes a
    structured CSV report. Each finding includes a severity prefix
    ([ERROR], [WARN], or [INFO]) in the detail field so characterisation
    is visible when the CSV is opened in a spreadsheet application.

    --input-dir DIR    Source CSV directory (default: current directory)
    --output FILE      Output CSV report path (default: audit_report.csv)

Severity levels:

- ``[ERROR]`` — Likely wrong, a data entry or housekeeping error with no 
  plausible legitimate explanation (e.g. validFrom after validTo, 
  completely identical duplicate rows).
- ``[WARN]`` — Possibly wrong. An unusual pattern that may have a legitimate
  operational explanation unknown to this tool (e.g. active rates for
  abolished classification codes, amendment chain date gaps).
- ``[INFO]`` — Noteworthy but not necessarily wrong. Patterns that are
  unusual from a data modelling perspective but may be normal practice
  (e.g. one-day transition rows, which NZ Customs uses routinely during
  rate changes).

Checks performed:

================================  =========  =================================
Check                             Severity   Description
================================  =========  =================================
``DATE_RANGE_INVERTED``           ERROR      validFrom is later than validTo
``DUPLICATE_ROW``                 ERROR      Identical code key and validFrom
                                             in Tariff_Details.csv
``DUPLICATE_RATE_ROW``            ERROR      Identical rate row including
                                             start and expiry dates
``DUPLICATE_LEVY_ROW``            ERROR      Identical levy row
``AMENDMENT_CHAIN_OVERLAP``       ERROR      Next version starts before
                                             current version expires
``ORPHANED_RATE``                 ERROR      Rate references a code not
                                             present anywhere in
                                             Tariff_Details.csv
``ORPHANED_LEVY``                 ERROR      As above, for levy rows
``UNKNOWN_FORMULA``               ERROR      Rate or levy references a
                                             formula code not in
                                             Tariff_Levy_Formulas.csv
``MALFORMED_CODE_LEVEL``          ERROR      Level field has wrong digit count
``ZOMBIE_RATE``                   WARNING    Active rate for a code whose
                                             classification rows have all
                                             expired
``ZOMBIE_LEVY``                   WARNING    As above, for levy rows
``AMENDMENT_CHAIN_GAP``           WARNING    Gap of more than one day between
                                             consecutive versions of a code
``MISSING_DESCRIPTION``           WARNING    Empty description field
``MISSING_SECTION``               WARNING    No section assigned
``ONE_DAY_ROW``                   INFO       validFrom equals validTo;
                                             normal NZ Customs transition
                                             practice
================================  =========  =================================

Note on audit findings
~~~~~~~~~~~~~~~~~~~~~~

The severity levels reflect the best assessment of this tool and are not
authoritative determinations. NZ Customs Service staff are the domain
experts and will have operational context that this tool does not have.
Some findings flagged as ERROR may have legitimate explanations; some
WARNING or INFO findings may be more significant than assessed here.

Findings are presented in good faith. NZ Customs is invited to confirm
or correct the characterisation of each finding type, identify findings
that reflect known intentional data patterns, and investigate findings
that may represent genuine data quality issues.

Results from the current dataset (as of March 2026, current-only mode)::

    Total findings: 15,515
      [ERROR]    118
      [WARN]   5,156
      [INFO]  10,241

    ONE_DAY_ROW                   10,241  INFO
    ZOMBIE_RATE                    5,146  WARN
    DUPLICATE_ROW                     50  ERROR
    AMENDMENT_CHAIN_OVERLAP           37  ERROR
    DATE_RANGE_INVERTED               26  ERROR
    AMENDMENT_CHAIN_GAP               10  WARN
    DUPLICATE_LEVY_ROW                 4  ERROR
    DUPLICATE_RATE_ROW                 1  ERROR


Architecture
------------

``hs_converter.py`` contains a base class and five subclasses::

    HSConverter                 Base class: CSV reading, YAML rendering,
                                date parsing, node factory, streaming write
    ├── HSSchemaConverter       → hs.yaml
    ├── TariffDetailsConverter  → tariff_details.yaml
    ├── TariffRatesConverter    → tariff_rates.yaml
    ├── TariffLeviesConverter   → tariff_levies.yaml
    └── LevyFormulasConverter   → tariff_levy_formulas.yaml

``convert.py`` is a thin CLI wrapper that runs selected converters,
in parallel by default using Python ``multiprocessing``.

``validate.py`` is an independent validation script requiring only
PyYAML; it does not import ``hs_converter``.


Related Resources
-----------------

- `WCO Harmonized System <https://www.wcoomd.org/en/topics/nomenclature/overview/what-is-the-harmonized-system.aspx>`_
- `WCO HS 2022 Nomenclature <https://www.wcoomd.org/en/topics/nomenclature/instrument-and-tools/hs-nomenclature-2022-edition.aspx>`_
- `NZ Customs Service Working Tariff <https://www.customs.govt.nz/business/tariffs/working-tariff-document/>`_
- `NZ Customs tariff classifications and rates <https://www.customs.govt.nz/business/tariffs/tariff-classifications-and-rates/>`_
- `UN Statistics Division HS classifications <https://unstats.un.org/unsd/classifications/Econ>`_

Note: The Kraken ontology (``kr:`` namespace) is a private knowledge
representation system. The ``kr:`` term references in the output YAML
are symbolic identifiers; the Kraken ontology itself is not included
in or distributed with this repository.


Licence
-------

Source code: MIT Licence.

Source data: No known rights — NZ Customs Service.
See `NZ Customs terms of use <https://www.customs.govt.nz/customs-information-and-legislation/about-this-website/terms-of-use/>`_.

Kraken ontology (``kr:`` namespace): Copyright 2017–2026 Ichiro Furusato.
Subject to the Neocortext Data Licence. The Kraken ontology is a private
system and is not included in or distributed with this repository. The
``kr:`` term identifiers used in the output YAML are references only.


.. _New Zealand Customs Service Working Tariff: https://www.customs.govt.nz/business/tariffs/tariff-classifications-and-rates/
.. _Harmonized Commodity Description and Coding System: https://www.wcoomd.org/en/topics/nomenclature/overview/what-is-the-harmonized-system.aspx
.. _World Customs Organization: https://www.wcoomd.org/

