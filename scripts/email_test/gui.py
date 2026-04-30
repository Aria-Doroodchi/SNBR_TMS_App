"""CustomTkinter window for the standalone email permissions test."""

from __future__ import annotations

import tempfile
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.user_settings import (
    load_defaults,
    save_defaults,
    KEY_SMTP_HOST,
    KEY_SMTP_PORT,
    KEY_EMAIL_USERNAME,
    KEY_EMAIL_FROM,
    KEY_EMAIL_DEFAULT_TO,
    KEY_EMAIL_DEFAULT_CC,
    KEY_EMAIL_DEFAULT_BCC,
    KEY_EMAIL_SUBJECT,
    KEY_EMAIL_BODY,
    KEY_EMAIL_REMEMBER_PASSWORD,
)
from emailing.credentials import (
    save_password, load_password, delete_password, keyring_backend_name,
)
from emailing.pdf_letterhead import build_sample_pdf
from emailing.smtp_sender import send_email_with_attachment
from gui.theme import (
    ACCENT_COLOR,
    ACCENT_HOVER,
    BUTTON_HEIGHT,
    CORNER_RADIUS,
    DISABLED_FG,
    ENTRY_HEIGHT,
    ERROR_COLOR,
    FONT_BODY,
    FONT_BUTTON,
    FONT_HEADING,
    FONT_SMALL,
    FONT_TITLE,
    PAD_X,
    PAD_Y,
    SUCCESS_COLOR,
)


def _split_addrs(raw: str) -> list[str]:
    return [a.strip() for a in raw.split(",") if a.strip()]


class EmailTestApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("SNBR TMS — Email Permissions Test")
        self.geometry("780x920")

        self._attachment_path: Path | None = None
        self._remember_var = ctk.BooleanVar(value=False)
        self._build_ui()
        self._load_defaults()

    # ---- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = ctk.CTkScrollableFrame(self, corner_radius=0)
        outer.pack(fill="both", expand=True)

        ctk.CTkLabel(
            outer, text="Email Permissions Test", font=FONT_TITLE,
        ).pack(pady=(PAD_Y * 2, 4), padx=PAD_X, anchor="w")
        ctk.CTkLabel(
            outer,
            text="Generate a sample letterheaded PDF and try to send it via SMTP.",
            font=FONT_SMALL,
        ).pack(pady=(0, PAD_Y * 2), padx=PAD_X, anchor="w")

        ctk.CTkLabel(outer, text="SMTP server", font=FONT_HEADING).pack(
            anchor="w", padx=PAD_X, pady=(PAD_Y, 4)
        )
        smtp_row = ctk.CTkFrame(outer, fg_color="transparent")
        smtp_row.pack(fill="x", padx=PAD_X)
        self.host_entry = self._entry(smtp_row, "smtp.gmail.com", width=360)
        self.host_entry.pack(side="left")
        self.port_entry = self._entry(smtp_row, "587", width=80)
        self.port_entry.pack(side="left", padx=(PAD_Y, 0))

        self.username_entry = self._labeled_entry(outer, "Username")
        self.password_entry = self._labeled_entry(outer, "Password", show="*")

        ctk.CTkCheckBox(
            outer, text="Remember password on this machine",
            variable=self._remember_var, font=FONT_SMALL,
            command=self._update_security_note,
        ).pack(anchor="w", padx=PAD_X, pady=(0, PAD_Y))

        self.from_entry = self._labeled_entry(outer, "From")
        self.to_entry = self._labeled_entry(outer, "To  (comma-separated)")
        self.cc_entry = self._labeled_entry(outer, "Cc  (comma-separated)")
        self.bcc_entry = self._labeled_entry(outer, "Bcc  (comma-separated)")
        self.subject_entry = self._labeled_entry(outer, "Subject")

        ctk.CTkLabel(outer, text="Body", font=FONT_HEADING).pack(
            anchor="w", padx=PAD_X, pady=(PAD_Y, 4)
        )
        self.body_box = ctk.CTkTextbox(outer, height=120, corner_radius=CORNER_RADIUS)
        self.body_box.pack(fill="x", padx=PAD_X)

        ctk.CTkLabel(outer, text="Attachment (PDF)", font=FONT_HEADING).pack(
            anchor="w", padx=PAD_X, pady=(PAD_Y * 2, 4)
        )
        att_row = ctk.CTkFrame(outer, fg_color="transparent")
        att_row.pack(fill="x", padx=PAD_X)
        self.attachment_entry = ctk.CTkEntry(
            att_row, height=ENTRY_HEIGHT, corner_radius=CORNER_RADIUS,
            font=FONT_BODY, state="readonly",
        )
        self.attachment_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            att_row, text="Generate sample", command=self._on_generate_pdf,
            width=140, height=BUTTON_HEIGHT, corner_radius=CORNER_RADIUS,
            font=FONT_BUTTON, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER,
        ).pack(side="left", padx=(PAD_Y, 0))
        ctk.CTkButton(
            att_row, text="Browse…", command=self._on_browse_pdf,
            width=90, height=BUTTON_HEIGHT, corner_radius=CORNER_RADIUS,
            font=FONT_BUTTON, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER,
        ).pack(side="left", padx=(PAD_Y, 0))

        # Buttons
        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.pack(fill="x", padx=PAD_X, pady=(PAD_Y * 2, PAD_Y))

        self.save_button = ctk.CTkButton(
            btn_row, text="Save defaults", command=self._on_save_defaults,
            height=BUTTON_HEIGHT + 6, corner_radius=CORNER_RADIUS,
            font=FONT_BUTTON, fg_color="transparent", border_width=1,
            border_color=ACCENT_COLOR, text_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
        )
        self.save_button.pack(side="left", padx=(0, PAD_Y))

        self.send_button = ctk.CTkButton(
            btn_row, text="Send email", command=self._on_send,
            height=BUTTON_HEIGHT + 6, corner_radius=CORNER_RADIUS,
            font=FONT_BUTTON, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER,
        )
        self.send_button.pack(side="right", fill="x", expand=True)

        self.security_label = ctk.CTkLabel(
            outer, text="", font=FONT_SMALL, text_color=DISABLED_FG,
            wraplength=720, justify="left",
        )
        self.security_label.pack(fill="x", padx=PAD_X, pady=(0, 4))

        self.status_label = ctk.CTkLabel(
            outer, text="", font=FONT_BODY, wraplength=720, justify="left",
        )
        self.status_label.pack(fill="x", padx=PAD_X, pady=(0, PAD_Y * 2))

    def _entry(self, parent, placeholder: str = "", width: int = 240, show: str = "") -> ctk.CTkEntry:
        return ctk.CTkEntry(
            parent, height=ENTRY_HEIGHT, corner_radius=CORNER_RADIUS,
            font=FONT_BODY, width=width, placeholder_text=placeholder, show=show,
        )

    def _labeled_entry(self, parent, label: str, show: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=FONT_HEADING).pack(
            anchor="w", padx=PAD_X, pady=(PAD_Y, 4)
        )
        e = ctk.CTkEntry(
            parent, height=ENTRY_HEIGHT, corner_radius=CORNER_RADIUS,
            font=FONT_BODY, show=show,
        )
        e.pack(fill="x", padx=PAD_X)
        return e

    # ---- Defaults -----------------------------------------------------------

    def _load_defaults(self) -> None:
        d = load_defaults()
        self.host_entry.insert(0, d.get(KEY_SMTP_HOST, "") or "smtp.gmail.com")
        self.port_entry.insert(0, d.get(KEY_SMTP_PORT, "") or "587")
        username = d.get(KEY_EMAIL_USERNAME, "")
        self.username_entry.insert(0, username)
        remember = d.get(KEY_EMAIL_REMEMBER_PASSWORD, "") == "1"
        self._remember_var.set(remember)
        if remember and username:
            pw = load_password(username) or ""
            if pw:
                self.password_entry.insert(0, pw)
        self.from_entry.insert(0, d.get(KEY_EMAIL_FROM, ""))
        self.to_entry.insert(0, d.get(KEY_EMAIL_DEFAULT_TO, ""))
        self.cc_entry.insert(0, d.get(KEY_EMAIL_DEFAULT_CC, ""))
        self.bcc_entry.insert(0, d.get(KEY_EMAIL_DEFAULT_BCC, ""))
        self.subject_entry.insert(
            0, d.get(KEY_EMAIL_SUBJECT, "") or "SNBR TMS — Email Permissions Test",
        )
        body_default = d.get(KEY_EMAIL_BODY, "") or (
            "Hello,\n\nAttached is a test PDF generated by the SNBR TMS email "
            "permissions probe. Please confirm receipt.\n"
        )
        self.body_box.insert("1.0", body_default)
        self._update_security_note()

    def _update_security_note(self) -> None:
        if self._remember_var.get():
            self.security_label.configure(
                text=f"Password will be stored encrypted in {keyring_backend_name()} "
                     "for the current OS user.",
            )
        else:
            self.security_label.configure(
                text="Password is not saved — you will need to enter it each session.",
            )

    # ---- Actions ------------------------------------------------------------

    def _set_attachment(self, path: Path) -> None:
        self._attachment_path = path
        self.attachment_entry.configure(state="normal")
        self.attachment_entry.delete(0, "end")
        self.attachment_entry.insert(0, str(path))
        self.attachment_entry.configure(state="readonly")

    def _on_generate_pdf(self) -> None:
        out_dir = Path(tempfile.gettempdir()) / "snbr_email_test"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"sample_{stamp}.pdf"
        try:
            build_sample_pdf(out_path)
        except Exception as e:  # noqa: BLE001
            self._set_status(f"PDF error — {type(e).__name__}: {e}", ok=False)
            return
        self._set_attachment(out_path)
        self._set_status(f"Sample PDF written to {out_path}", ok=True)

    def _on_browse_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self._set_attachment(Path(path))

    def _on_save_defaults(self) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        remember = self._remember_var.get()
        try:
            save_defaults(**{
                KEY_SMTP_HOST: self.host_entry.get().strip(),
                KEY_SMTP_PORT: self.port_entry.get().strip(),
                KEY_EMAIL_USERNAME: username,
                KEY_EMAIL_FROM: self.from_entry.get().strip(),
                KEY_EMAIL_DEFAULT_TO: self.to_entry.get().strip(),
                KEY_EMAIL_DEFAULT_CC: self.cc_entry.get().strip(),
                KEY_EMAIL_DEFAULT_BCC: self.bcc_entry.get().strip(),
                KEY_EMAIL_SUBJECT: self.subject_entry.get().strip(),
                KEY_EMAIL_BODY: self.body_box.get("1.0", "end").strip(),
                KEY_EMAIL_REMEMBER_PASSWORD: "1" if remember else "",
            })
            if remember and username and password:
                save_password(username, password)
            elif username:
                delete_password(username)
        except Exception as e:  # noqa: BLE001
            self._set_status(f"Save failed — {type(e).__name__}: {e}", ok=False)
            return
        self._update_security_note()
        msg = "Defaults saved."
        if remember:
            msg += f" Password stored in {keyring_backend_name()}."
        self._set_status(msg, ok=True)

    def _on_send(self) -> None:
        try:
            host = self.host_entry.get().strip()
            port_text = self.port_entry.get().strip()
            from_addr = self.from_entry.get().strip()
            to_addrs = _split_addrs(self.to_entry.get())
            cc_addrs = _split_addrs(self.cc_entry.get())
            bcc_addrs = _split_addrs(self.bcc_entry.get())
            subject = self.subject_entry.get().strip()
            body = self.body_box.get("1.0", "end").strip()
            username = self.username_entry.get().strip()
            password = self.password_entry.get()

            if not host:
                raise ValueError("SMTP host is required.")
            if not port_text.isdigit():
                raise ValueError("SMTP port must be an integer.")
            port = int(port_text)
            if not from_addr:
                raise ValueError("From address is required.")
            if not to_addrs:
                raise ValueError("At least one To address is required.")
            if self._attachment_path is None or not self._attachment_path.is_file():
                raise ValueError("Generate or browse to a PDF attachment first.")
        except ValueError as e:
            self._set_status(str(e), ok=False)
            return

        self.send_button.configure(state="disabled", text="Sending…")
        self._set_status("Connecting to SMTP server…", ok=None)

        def worker() -> None:
            try:
                send_email_with_attachment(
                    smtp_host=host, smtp_port=port,
                    username=username, password=password,
                    from_addr=from_addr,
                    to_addrs=to_addrs, cc_addrs=cc_addrs, bcc_addrs=bcc_addrs,
                    subject=subject, body=body,
                    attachment_path=self._attachment_path,
                )
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
                self.after(0, lambda: self._finish_send(False, err))
                return
            self.after(0, lambda: self._finish_send(True, "Sent — check inbox."))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_send(self, ok: bool, message: str) -> None:
        self.send_button.configure(state="normal", text="Send email")
        self._set_status(message, ok=ok)

    def _set_status(self, message: str, ok: bool | None) -> None:
        if ok is True:
            color = SUCCESS_COLOR
        elif ok is False:
            color = ERROR_COLOR
        else:
            color = DISABLED_FG
        self.status_label.configure(text=message, text_color=color)
