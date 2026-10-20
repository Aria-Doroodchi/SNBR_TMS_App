"""SNBR Report Dispatch — bind patient identity to exported reports and track sends.

The sister application of the analysis app. It never touches the DataFrame
or the archive CSV: it reads the *exported* report PDFs, the lab's enrolment
workbook, and an append-only ledger, and produces a hand-off folder of
identified PDFs. Sending is the operator's job, done by hand outside the app;
the app records which reports they declare sent and which are still waiting.

Backend rule, same as the rest of the project: nothing in this package imports
``gui/`` or ``dispatch_gui/``. Everything here runs headless.
"""
