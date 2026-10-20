"""SNBR Clinical Reports -- identified participant reports from the archive.

The third application in this repository, for the clinical collaborators on
the Sunnybrook side. It never parses a ``.MEM`` file: it opens the archive
CSV the analysis app exported (the full data frame) and the lab's enrolment
workbook (the master log), lets the user find a patient by **name, MRN or
study ID**, draws the same graphs the analysis app draws, and writes a report
PDF whose cover carries the patient's identity.

Backend rule, same as ``dispatch/``: nothing in this package imports ``gui/``,
``dispatch_gui/`` or ``clinical_gui/``. The graph pipeline itself lives in
``gui.controller.AppController`` and is reached only from
``clinical_gui/controller.py``.

What this package may import from the other apps, and why:

* ``dispatch.identity`` / ``dispatch.roster`` -- the ``(study, number)`` key
  and the read-only enrolment-workbook reader, so a patient is matched to the
  data exactly as the dispatch app matches a report to the roster.
* ``dispatch.stamp`` -- the cover-page identity box, so a report identified
  here looks the same as one identified by the dispatch app.
* ``reports.export_naming`` / ``reports.pdf_renderer`` -- the de-identified
  file names and the PDF assembly.
* ``processing.cohort_filters`` -- which study a visit belongs to.

Name and MRN never enter the DataFrame; they exist in the stamped PDF and its
file name only.
"""
