import re
import io
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any


def parse_fns_qr_string(qr_data: str) -> Tuple[Optional[Decimal], Optional[date], Optional[str]]:
    """
    Parses standard FNS QR string: t=20260803T153000&s=1250.50&fn=...&i=...&fp=...&n=1
    Returns (amount, date, note_text).
    """
    if not qr_data:
        return None, None, None

    data_clean = qr_data.strip()

    # Extract sum s=...
    sum_match = re.search(r'\bs=([\d\.]+)\b', data_clean)
    amount = None
    if sum_match:
        try:
            raw_s = sum_match.group(1)
            amount = Decimal(raw_s)
        except Exception:
            pass

    # Extract date t=... (e.g. t=20260803T153000 or t=20260803T1530)
    time_match = re.search(r'\bt=(\d{8})T(\d{4,6})\b', data_clean)
    receipt_date = date.today()
    if time_match:
        d_str = time_match.group(1)
        try:
            receipt_date = datetime.strptime(d_str, "%Y%m%d").date()
        except Exception:
            pass

    if amount and amount > 0:
        return amount, receipt_date, "Покупка по чеку (QR)"

    return None, None, None


def decode_qr_from_bytes(image_bytes: bytes) -> Optional[str]:
    """
    Decodes QR code text from image bytes if opencv/pyzbar/qreader is available.
    Returns decoded string or None.
    """
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        img_np = np.array(img)

        # 1. Try OpenCV QRCodeDetector
        try:
            import cv2
            detector = cv2.QRCodeDetector()
            val, pts, _ = detector.detectAndDecode(img_np)
            if val:
                return val
        except Exception:
            pass

        # 2. Try pyzbar
        try:
            from pyzbar.pyzbar import decode
            decoded_objs = decode(img)
            for obj in decoded_objs:
                if obj.data:
                    return obj.data.decode("utf-8")
        except Exception:
            pass

        # 3. Try qreader
        try:
            from qreader import QReader
            qreader = QReader()
            decoded_texts = qreader.detect_and_decode(image=img_np)
            for txt in decoded_texts:
                if txt:
                    return txt
        except Exception:
            pass

    except Exception:
        pass

    return None

