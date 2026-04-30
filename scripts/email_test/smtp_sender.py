"""Re-export of the promoted sender. Real code lives in emailing/smtp_sender.py."""

from emailing.smtp_sender import send_email_with_attachment

__all__ = ["send_email_with_attachment"]
