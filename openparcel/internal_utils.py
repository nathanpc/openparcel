#!/usr/bin/env python3

import datetime


def is_datetime_aware(dt: datetime.datetime) -> bool:
    """Checks if a datetime object is offset aware or not."""
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None
