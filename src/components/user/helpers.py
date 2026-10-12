"""
Helper utilities for the user component.
"""

import io
import pandas as pd
from pandas.errors import ParserError

from src.components.user.constants import (
    BulkUploadColumns,
    TextPrompt,
    ValidationMsg,
)


def safe_dict(obj) -> dict:
    """
    Return obj.__dict__ with password fields masked (******), safe for logging.
    Prevents hashed_password from appearing in plain text in any log line.
    """
    return {
        field_name: "******" if "password" in field_name.lower() else field_value
        for field_name, field_value in obj.__dict__.items()
    }


# =========================================================
# FILE-FORMAT SPECIFIC READERS
# Separate methods for CSV vs Excel parsing, per review
# comment on validate_csv_content — every other bulk-upload
# validator below reuses these instead of re-implementing
# its own if/else on filename.
# =========================================================
def _read_csv_dataframe(file_bytes: bytes, nrows: int | None = None) -> pd.DataFrame:
    """
    Parse an uploaded CSV file into a DataFrame.
    """
    return pd.read_csv(
        io.BytesIO(file_bytes),
        nrows=nrows,
        engine="python",
    )


def _read_excel_dataframe(file_bytes: bytes, nrows: int | None = None) -> pd.DataFrame:
    """
    Parse an uploaded Excel (.xlsx) file into a DataFrame.
    """
    return pd.read_excel(io.BytesIO(file_bytes), nrows=nrows)


def _read_dataframe(file_bytes: bytes, filename: str, nrows: int | None = None) -> pd.DataFrame:
    """
    Dispatch to the correct format-specific reader based on filename extension.
    """
    if filename.endswith(".xlsx"):
        return _read_excel_dataframe(file_bytes, nrows=nrows)
    return _read_csv_dataframe(file_bytes, nrows=nrows)


def validate_bulk_upload_headers(
    file_bytes: bytes,
    filename: str,
    flags: dict,
) -> None:
    """
    Validate bulk upload headers based on partner feature flags.
    """

    required_columns = BulkUploadColumns.MANDATORY

    df = _read_dataframe(file_bytes, filename, nrows=0)

    # Validate mandatory columns
    for column in required_columns:
        if column not in df.columns:
            raise ValueError(
                ValidationMsg.MANDATORY_COLUMNS_MISSING.format(column=column)
            )

    # Reject conditional columns if feature is disabled
    for column, flag_name in BulkUploadColumns.CONDITIONAL.items():
        if column in df.columns and not flags.get(flag_name, False):
            raise ValueError(
                f"Column '{column}' cannot be used because this feature is not enabled."
            )


def validate_bulk_upload_file(file_bytes: bytes, filename: str) -> None:
    """
    Validate that the uploaded CSV/Excel file is not empty.
    Raises ValueError if the file contains no headers or no data.
    """

    try:
        df = _read_dataframe(file_bytes, filename)
    except pd.errors.EmptyDataError:
        raise ValueError(TextPrompt.FILE_EMPTY)

    if df.empty:
        raise ValueError(TextPrompt.FILE_EMPTY)


def validate_bulk_upload_data_rows(file_bytes: bytes, filename: str) -> None:
    """
    Validate that the uploaded file contains at least one data row.
    """

    df = _read_dataframe(file_bytes, filename)

    if df.empty:
        raise ValueError(ValidationMsg.NO_USER_RECORDS)


def _validate_csv_structure(df: pd.DataFrame) -> None:
    """
    CSV-only structural check: catch a JSON file that was merely renamed
    to .csv (its first "column" ends up looking like a JSON key/brace).
    Not applicable to Excel files, since xlsx can't be JSON-renamed.
    """
    first_column = str(df.columns[0]).strip()
    if (
        first_column.startswith("{")
        or first_column.startswith("[")
        or first_column.endswith("}")
        or first_column.endswith("]")
    ):
        raise ValueError(ValidationMsg.INVALID_CSV_FORMAT)


def validate_csv_content(file_bytes: bytes, filename: str) -> None:
    """
    Validate that the uploaded file (CSV or Excel) contains valid, parseable content.
    """
    try:
        df = _read_dataframe(file_bytes, filename, nrows=5)
    except (ParserError, UnicodeDecodeError):
        raise ValueError(ValidationMsg.INVALID_CSV_FORMAT)
    except Exception:
        raise ValueError(ValidationMsg.INVALID_CSV_FORMAT)

    if len(df.columns) == 0:
        raise ValueError(ValidationMsg.INVALID_CSV_FORMAT)

    # JSON-renamed-as-CSV check only makes sense for actual CSV files
    if not filename.endswith(".xlsx"):
        _validate_csv_structure(df)