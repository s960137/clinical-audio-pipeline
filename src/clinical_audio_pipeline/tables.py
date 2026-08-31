"""Strict public schemas. Errors refer to row numbers, never source values."""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd


VISIT_COLUMNS = ["row_id", "subject_id", "visit_id", "recorded_at"]
RECORDING_COLUMNS = ["recording_id", "subject_id", "recorded_at", "source_url"]
ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
NATIONAL_ID_PATTERN = re.compile(r"[A-Z][12][0-9]{8}\Z", re.I)


def opaque_id(value):
    value = str(value).strip()
    if not ID_PATTERN.fullmatch(value) or NATIONAL_ID_PATTERN.fullmatch(value):
        raise ValueError("Use opaque identifiers; national identification numbers are forbidden")
    return value


def timestamp(value):
    """Explicit local wall time only; no silent midnight or timezone conversion."""
    value = str(value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?", value):
        raise ValueError("timestamp_requires_explicit_local_time")
    return datetime.fromisoformat(value)


def read_table(path, columns, unique_key):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        table = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif path.suffix.lower() == ".xlsx":
        table = pd.read_excel(path, dtype=str, keep_default_na=False)
    else:
        raise ValueError("Only CSV and XLSX inputs are supported")
    if set(table.columns) != set(columns):
        raise ValueError("Input columns must exactly match the documented schema")
    table = table.loc[:, columns].fillna("").copy()
    for column in [c for c in columns if c.endswith("_id")]:
        for index, value in enumerate(table[column]):
            try:
                table.loc[index, column] = opaque_id(value)
            except ValueError:
                raise ValueError(f"Invalid opaque identifier in input row {index + 1}") from None
    if table[unique_key].duplicated().any():
        raise ValueError("Duplicate primary identifiers in input table")
    return table
