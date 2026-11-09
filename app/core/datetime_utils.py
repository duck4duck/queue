from datetime import datetime, timezone


def parse_utc_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-formatted datetime string and ensure it has UTC timezone."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None
