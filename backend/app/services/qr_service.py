"""QR code generation for component passports.

The encoded payload is the **DPP resolver URL**, not the local viewer URL. A
label is printed once and glued to a component that outlives several
generations of web application; encoding ``http://localhost:5173/...`` produces
a passport whose link dies when the demo server stops, which is not a passport.
The resolver URL carries the persistent identifier, so the label survives any
change of hosting. See :mod:`app.services.dpp_service`.

Older labels encoding a bare component id or the local passport URL still
resolve - :func:`parse_scanned_value` accepts all three forms.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Dict, Optional

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.core.config import settings
from app.services import dpp_service

#: Rendering defaults tuned for printing on a component label.
BOX_SIZE = 10
BORDER = 2


def passport_url(component_id: str) -> str:
    """Local viewer URL for a component passport.

    This is where the app's own UI navigates. It is deliberately *not* what
    the QR code encodes - see :func:`qr_payload_value`.
    """
    return f"{settings.qr_passport_base}/{component_id}"


def qr_payload_value(component_id: str) -> str:
    """The string actually encoded into a printed QR label."""
    return dpp_service.resolver_url(component_id)


def build_qr_image(data: str, box_size: int = BOX_SIZE, border: int = BORDER):
    """Return a PIL image for the given payload."""
    code = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    code.add_data(data)
    code.make(fit=True)
    return code.make_image(fill_color="#0B1F3A", back_color="white")


def qr_png_bytes(component_id: str, box_size: int = BOX_SIZE, border: int = BORDER) -> bytes:
    """Render the passport QR code for a component as PNG bytes."""
    buffer = BytesIO()
    build_qr_image(qr_payload_value(component_id), box_size=box_size, border=border).save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def qr_data_uri(component_id: str, box_size: int = 6, border: int = BORDER) -> str:
    """Render the QR code as a base64 ``data:`` URI for inline embedding."""
    encoded = base64.b64encode(qr_png_bytes(component_id, box_size=box_size, border=border)).decode()
    return f"data:image/png;base64,{encoded}"


def qr_payload(component_id: str, qr_token: Optional[str] = None) -> Dict[str, Any]:
    """Metadata describing a component QR code (used by the passport API)."""
    return {
        "component_id": component_id,
        "qr_token": qr_token,
        "passport_url": passport_url(component_id),
        "encoded_payload": qr_payload_value(component_id),
        "dpp_id": dpp_service.default_identifier(component_id),
        "qr_image_url": f"{settings.API_V1_PREFIX}/passports/{component_id}/qr",
        "format": "PNG",
        "error_correction": "M",
    }


def parse_scanned_value(value: str) -> Optional[str]:
    """Extract a component id from a scanned QR payload.

    Accepts a DPP resolver URL or URN, a passport URL, a bare component id, or
    a ``KE-...`` token embedded in arbitrary text, so a technician can scan
    labels produced by any generation of the tool.
    """
    if not value:
        return None
    candidate = value.strip()
    from_dpp = dpp_service.parse_identifier(candidate)
    if from_dpp:
        return from_dpp
    if "/" in candidate:
        candidate = candidate.rstrip("/").split("/")[-1]
    candidate = candidate.split("?")[0].split("#")[0]
    return candidate or None
