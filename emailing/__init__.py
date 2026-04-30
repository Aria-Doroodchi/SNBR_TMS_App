"""Email delivery for SNBR TMS reports."""

from emailing.smtp_sender import send_email_with_attachment
from emailing.credentials import (
    SERVICE_NAME,
    save_password,
    load_password,
    delete_password,
    keyring_backend_name,
)

__all__ = [
    "send_email_with_attachment",
    "SERVICE_NAME",
    "save_password",
    "load_password",
    "delete_password",
    "keyring_backend_name",
]
