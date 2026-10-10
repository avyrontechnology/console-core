"""Utilities for building the bulk-upload reference CSV header row."""

from typing import Dict, List

from src.components.user.constants import BulkUploadColumns


def build_bulk_upload_headers(flags: Dict[str, bool]) -> List[str]:
    # Mandatory columns
    headers = list(BulkUploadColumns.MANDATORY)
    # Optional columns
    headers.extend(BulkUploadColumns.OPTIONAL)
    # Conditional columns
    if flags.get("is_teams_enabled"):
        headers.append(BulkUploadColumns.TEAM)

    if flags.get("is_partner_custom_roles_enabled"):
        headers.append(BulkUploadColumns.CUSTOM_ROLE)

    return headers