"""
Combine a session's vital-sign entries into one current picture.

A nurse often records observations in separate entries (temperature at 14:05, an AVPU
check at 14:12). Each entry is a row with only the fields that were actually measured.
Reading only the newest row would silently drop everything measured earlier — an
"Unresponsive" reading would vanish the moment someone later saved a temperature.

So for each field we take the most recent value that was actually recorded. A field
nobody recorded stays None (unknown); it is never defaulted to a normal-looking value.
"""

from types import SimpleNamespace
from typing import Iterable, Optional

VITAL_FIELDS = (
    "temperature", "pulse", "systolic_bp", "diastolic_bp",
    "respiratory_rate", "spo2", "pain_score", "gcs", "avpu",
)


def merge_latest_vitals(rows: Iterable) -> Optional[SimpleNamespace]:
    """`rows` must be ordered newest first. Returns None if there are no entries."""
    rows = list(rows)
    if not rows:
        return None
    merged = {field: None for field in VITAL_FIELDS}
    for row in rows:
        for field in VITAL_FIELDS:
            value = getattr(row, field, None)
            if merged[field] is None and value is not None and value != "":
                merged[field] = value
    merged["entered_by"] = rows[0].entered_by
    merged["recorded_at"] = rows[0].recorded_at
    return SimpleNamespace(**merged)
