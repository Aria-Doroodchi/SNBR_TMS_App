# SNBR TMS App

A Windows desktop application for the ALS Neurophysiology and Neuromodulation Lab that
parses transcranial magnetic stimulation (TMS) measurement files (`.MEM`) produced by
Qtrack sessions, extracts TMS metrics, builds analysis-ready dataframes, and generates
PDF reports that benchmark participants against healthy-control and ALS reference groups.
It runs fully offline on lab Windows machines and is packaged with PyInstaller.

See [`gui/README.md`](gui/README.md) for a GUI quick-start.

Two companion applications are built from the same tree:

- **SNBR Report Dispatch** (`dispatch_main.py`, `build_dispatch.bat`) — binds patient identity from the
  lab's enrolment workbook to exported report PDFs and tracks which have been sent.
- **SNBR Clinical Reports** (`clinical_main.py`, `build_clinical.bat`) — for clinical collaborators: opens
  the exported data-frame CSV and the enrolment workbook, finds a patient by name, MRN or study ID,
  draws the same graphs as the analysis app, and exports a report with the patient's identity on its
  cover. It does not parse `.MEM` files.

## License

Released under the [PolyForm Noncommercial License 1.0.0](LICENSE): free to use,
modify, and redistribute **for noncommercial purposes** — research, teaching, personal
study, and use by academic, nonprofit, public-research, and government organizations
(regardless of funding source) — provided the copyright and license notices are kept
intact. **Commercial use is not granted by this license.**

Copyright (c) 2026 Ali Doroodchi, ALS Neurophysiology and Neuromodulation Lab

## Citation

If you use this software or its results in academic work, please cite it. GitHub's
**"Cite this repository"** sidebar (from [`CITATION.cff`](CITATION.cff)) exports APA
and BibTeX entries.
