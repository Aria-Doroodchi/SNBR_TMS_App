"""Re-export of the promoted helper. Real code lives in emailing/pdf_letterhead.py."""

from emailing.pdf_letterhead import build_sample_pdf

__all__ = ["build_sample_pdf"]
