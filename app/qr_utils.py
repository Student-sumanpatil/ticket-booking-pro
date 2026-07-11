from pathlib import Path

import qrcode

QR_DIR = Path(__file__).resolve().parent.parent / "tickets_qr"
QR_DIR.mkdir(exist_ok=True)


def generate_ticket_qr(booking_reference: str) -> str:
    """
    Encodes the booking reference into a QR code image and saves it.
    Returns the relative file path (used to serve/attach it later).
    In a real deployment, this data could instead be a signed URL that
    an usher's scanner app calls to validate + check in the ticket.
    """
    img = qrcode.make(f"CINEBOOK-TICKET:{booking_reference}")
    file_path = QR_DIR / f"{booking_reference}.png"
    img.save(file_path)
    return str(file_path)
