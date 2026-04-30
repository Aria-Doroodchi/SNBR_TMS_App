"""SMTP send with PDF attachment. Stdlib only."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def send_email_with_attachment(
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addrs: list[str],
    cc_addrs: list[str],
    bcc_addrs: list[str],
    subject: str,
    body: str,
    attachment_path: Path,
) -> None:
    attachment_path = Path(attachment_path)
    if not attachment_path.is_file():
        raise FileNotFoundError(f"Attachment not found: {attachment_path}")

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg["Subject"] = subject
    msg.set_content(body or "")

    pdf_bytes = attachment_path.read_bytes()
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_path.name,
    )

    all_recipients = list(to_addrs) + list(cc_addrs) + list(bcc_addrs)
    context = ssl.create_default_context()

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as s:
            if username:
                s.login(username, password)
            s.send_message(msg, from_addr=from_addr, to_addrs=all_recipients)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
            s.ehlo()
            s.starttls(context=context)
            s.ehlo()
            if username:
                s.login(username, password)
            s.send_message(msg, from_addr=from_addr, to_addrs=all_recipients)
