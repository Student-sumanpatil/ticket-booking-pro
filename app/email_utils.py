"""
Email delivery abstraction.

Two backends, switched via the EMAIL_BACKEND env var:

- "console" (default): no credentials needed. Every email is logged to
  stdout AND saved as an .html file under sent_emails/, so graders can
  open it in a browser and see exactly what would have been sent.
- "smtp": sends a real email using any SMTP provider - Gmail (with an
  App Password), SendGrid, Mailtrap, etc. Configure SMTP_* in .env.
"""
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.config import settings

SENT_DIR = Path(__file__).resolve().parent.parent / "sent_emails"
SENT_DIR.mkdir(exist_ok=True)


def send_email(to: str, subject: str, html_body: str, attachment_path: str | None = None) -> None:
    if settings.EMAIL_BACKEND == "smtp":
        _send_via_smtp(to, subject, html_body, attachment_path)
    else:
        _send_via_console(to, subject, html_body, attachment_path)


def _send_via_console(to: str, subject: str, html_body: str, attachment_path: str | None) -> None:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    safe_to = to.replace("@", "_at_").replace(".", "_")
    file_path = SENT_DIR / f"{timestamp}_{safe_to}.html"
    note = f"<p><em>[Attachment would be: {attachment_path}]</em></p>" if attachment_path else ""
    file_path.write_text(
        f"<h3>To: {to}</h3><h3>Subject: {subject}</h3><hr>{html_body}{note}"
    )
    print(f"[email:console] to={to} subject={subject!r} saved={file_path}")


def _send_via_smtp(to: str, subject: str, html_body: str, attachment_path: str | None) -> None:
    msg = MIMEMultipart()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    if attachment_path:
        from email.mime.image import MIMEImage
        with open(attachment_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-Disposition", "attachment", filename=Path(attachment_path).name)
            msg.attach(img)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, [to], msg.as_string())
