import asyncio
import base64
import io
from typing import Dict, Any, List, Optional, Tuple, TypedDict, Set
import re
import uuid
from uuid import UUID
from src.components.auth.constant import AuthExceptionMsg

import pandas as pd
from src.components.user.models import User
from src.components.auth.error import UserCreatedButEmailFailedError
from src.components.user.repositories import UserRepository
from src.components.auth.service import AuthService
from src.components.user.constants import ValidationMsg, UserDefaults, RowProcessResult
from src.components.auth.schema import UserData
from src.console_celery.celery_app import celery
from src.loggers.console_celery_logger import CeleryLogger
from src.components.location.repositories import LocationRepository
from src.components.auth.repositories import AuthRepository

logger = CeleryLogger.get_logger()


class LocationData(TypedDict):
    country_id: Optional[UUID]
    state_id: Optional[UUID]
    city_id: Optional[UUID]


class BulkUserResponse(TypedDict):
    total_success_count: int
    total_failed_count: int
    failed_reasons: List[Dict[str, Any]]


class CurrentUser(TypedDict):
    user_id: UUID


RowResult = Tuple[int, Dict[str, Any], Optional[RowProcessResult], Optional[int], Optional[Exception]]


# =========================================================
# HELPER: GET ATTR OR KEY
# Safely access .attr or ["key"] from ORM objects or dicts
# =========================================================
def _get_id(obj: Any) -> Optional[int]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get("id")
    return getattr(obj, "id", None)


def _get_name(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get("name")
    return getattr(obj, "name", None)


def _get_country_id(obj: Any) -> Optional[int]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get("country_id")
    return getattr(obj, "country_id", None)


def _get_state_id(obj: Any) -> Optional[int]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get("state_id")
    return getattr(obj, "state_id", None)


# =========================================================
# HELPER: WRITE RESULT FILE
# =========================================================
def _convert_result_to_bytes(rows_result: List[Dict[str, Any]]) -> bytes:
    if not rows_result:
        return b""
    df = pd.DataFrame(rows_result)

    if "row_number" in df.columns:
        df = df.drop(columns=["row_number"])

    if "parent" in df.columns:
        df = df.drop(columns=["parent"])

    return df.to_csv(index=False).encode("utf-8-sig")


# =========================================================
# HELPER: PARENT COLUMN
# 'parent' holds the parent user's EMAIL — the only field guaranteed
# unique in the system. A name can't be used because two different
# people can share a name; email always identifies exactly one user,
# whether that user already exists in the DB or is being created a few
# rows above/below in this same file.
# =========================================================
def _clean_parent_ref(value: Any) -> Optional[str]:
    """
    Returns a normalized (trimmed, lowercased) email string, or None if
    the cell is empty — an empty cell means "assign the default Admin",
    exactly like before this feature existed.
    """
    if pd.isna(value) or not str(value).strip():
        return None
    return str(value).strip().lower()


# =========================================================
# HELPER: READ CSV / XLSX
# =========================================================
def _read_file(file_data: bytes, filename: str) -> pd.DataFrame:
    last_error: Optional[Exception] = None

    for encoding in ["utf-8", "latin-1", "ISO-8859-1"]:
        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(
                    io.BytesIO(file_data),
                    encoding=encoding,
                    engine="python",
                )
            else:
                df = pd.read_excel(
                    io.BytesIO(file_data),
                )

            break
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    else:
        raise ValueError(f"Could not decode file: {last_error}")

    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty:
        raise ValueError("File is empty")

    # Normalize column headers (case/whitespace-insensitive). Uploaded
    # files are often hand-edited in Excel/WPS — a header typed as
    # "Parent", "PARENT", or " parent " must still map to the "parent"
    # column below, or its data gets silently dropped and every row
    # falls back to the default admin.
    df.columns = [str(col).strip().lower() for col in df.columns]

    required_columns: List[str] = ["email", "phone_number", "name", "role"]
    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    optional_columns: List[str] = [
        "country", "state", "city",
        "designation", "alternate_phone_number",
        "cloud_agent_number", "parent",
    ]

    for col in optional_columns:
        if col not in df.columns:
            df[col] = None

    # Detect duplicate emails within the CSV and mark them upfront
    email_col = df["email"].astype(str).str.strip().str.lower()
    df["_duplicate_email"] = email_col.duplicated(keep="first")
    df["_row_email"] = email_col
    df["_parent_ref"] = df["parent"].apply(_clean_parent_ref)

    # Diagnostic only — counts, never raw emails, so this is safe to keep
    # in production logs permanently. If this ever prints "0 of N" while
    # you DID fill in parent values, the uploaded file's header for the
    # parent column doesn't match what's expected.
    logger.info(
        "Parent column check: %s of %s rows have a parent value",
        df["_parent_ref"].notna().sum(), len(df),
    )

    logger.info("File read successfully with encoding=%s", encoding)
    return df


# =========================================================
# HELPER: CLEAN EMAIL
# =========================================================
def _clean_email(email: Optional[str]) -> str:
    if pd.isna(email) or not str(email).strip():
        raise ValueError(ValidationMsg.EMAIL_REQUIRED)

    email = str(email).strip().replace("\n", "").replace("\r", "").replace(" ", "").lower()

    EMAIL_REGEX: str = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(EMAIL_REGEX, email):
        raise ValueError(ValidationMsg.INVALID_EMAIL)

    return email


# =========================================================
# HELPER: CLEAN PHONE
# =========================================================
def _clean_phone(phone: Optional[str]) -> str:
    if pd.isna(phone):
        raise ValueError(ValidationMsg.PHONE_REQUIRED)

    # Keep digits only (+91... → 91...)
    phone_str: str = str(phone).strip().split(".")[0]
    phone_str = "".join(ch for ch in phone_str if ch.isdigit())

    if not phone_str:
        raise ValueError(ValidationMsg.PHONE_REQUIRED)

    if len(phone_str) == 10:
        return "+91" + phone_str

    if len(phone_str) == 12 and phone_str.startswith("91"):
        return "+91" + phone_str[2:]

    raise ValueError(ValidationMsg.INVALID_PHONE)


# =========================================================
# VALIDATION HELPERS
# =========================================================
def _get_optional_str(value: Any) -> Optional[str]:
    if pd.isna(value) or not str(value).strip():
        return None
    return str(value).strip().lower()


def _get_password(value: Any) -> str:
    if pd.isna(value) or not str(value).strip():
        return UserDefaults.PASSWORD
    return str(value).strip()


# =========================================================
# BASIC FIELD VALIDATION
# =========================================================
def _validate_basic_fields(row: pd.Series) -> Tuple[str, str, str, str]:
    errors = []

    # EMAIL
    try:
        email = _clean_email(row.get("email"))
    except Exception as e:
        errors.append(str(e))
        email = None

    # NAME
    name_raw = row.get("name")
    if pd.isna(name_raw) or not str(name_raw).strip():
        errors.append(ValidationMsg.NAME_REQUIRED)
        name = None
    else:
        name = str(name_raw).strip()

    # PHONE
    try:
        phone = _clean_phone(row.get("phone_number"))
    except Exception as e:
        errors.append(str(e))
        phone = None

    # PASSWORD — default is applied silently; caller can warn if needed
    password = _get_password(row.get("password"))

    if errors:
        raise ValueError(errors[0])

    return email, name, phone, password


# =========================================================
# ROLE — parent is resolved separately (see _build_parent_plan /
# _process_rows_with_parent_resolution); this only resolves the Role row.
# =========================================================
def _get_role(row: pd.Series, role_map: Dict[str, Any]) -> Any:
    role_name: Optional[str] = _get_optional_str(row.get("role"))
    if not role_name:
        raise ValueError(ValidationMsg.ROLE_REQUIRED)
    role: Any = role_map.get(role_name)
    if not role:
        raise ValueError(f"Invalid role: '{role_name}'. Check the role name matches an existing role exactly.")
    return role


# =========================================================
# LOCATION HELPERS
# Unified access via _get_id / _get_name helpers so both
# dicts (get_all_countries) and ORM objects (get_all_states /
# get_all_cities) are handled transparently.
# =========================================================
def _validate_location_fields(
    country_name: Optional[str],
    state_name: Optional[str],
    city_name: Optional[str],
) -> None:
    if country_name or state_name or city_name:
        if not (country_name and state_name and city_name):
            raise ValueError(
                "Please provide all 3 location fields: country, state and city"
            )


def _resolve_country(
    country_name: Optional[str],
    country_map: Dict[str, Any],
) -> Optional[Any]:
    if not country_name:
        return None
    country = country_map.get(country_name)
    if not country:
        raise ValueError(f"Invalid country: '{country_name}'")
    return country


def _resolve_state(
    state_name: Optional[str],
    state_map: Dict[Tuple[str, int], Any],
    country: Optional[Any],
) -> Optional[Any]:
    if not state_name:
        return None
    country_id = _get_id(country)
    state = state_map.get((state_name, country_id)) if country_id is not None else None
    if not state:
        raise ValueError(f"Invalid state: {state_name}")
    return state


def _resolve_city(
    city_name: Optional[str],
    city_map: Dict[Tuple[str, int], Any],
    state: Optional[Any],
) -> Optional[Any]:
    if not city_name:
        return None
    state_id = _get_id(state)
    city = city_map.get((city_name, state_id)) if state_id is not None else None
    if not city:
        raise ValueError(f"Invalid city: '{city_name}'")
    return city


def _get_location_ids(
    row: pd.Series,
    country_map: Dict[str, Any],
    state_map: Dict[Tuple[str, int], Any],
    city_map: Dict[Tuple[str, int], Any],
) -> LocationData:
    country_name = _get_optional_str(row.get("country"))
    state_name = _get_optional_str(row.get("state"))
    city_name = _get_optional_str(row.get("city"))

    _validate_location_fields(country_name, state_name, city_name)

    country = _resolve_country(country_name, country_map)
    state = _resolve_state(state_name, state_map, country)
    city = _resolve_city(city_name, city_map, state)

    return {
        "country_id": _get_id(country),
        "state_id": _get_id(state),
        "city_id": _get_id(city),
    }


def _get_extra_fields(row: pd.Series) -> Dict[str, Any]:
    designation: Optional[str] = _get_optional_str(row.get("designation"))

    alt_phone: Optional[str] = _get_optional_str(row.get("alternate_phone_number"))
    if alt_phone:
        alt_phone = _clean_phone(alt_phone)

    cloud_agent: Optional[str] = _get_optional_str(row.get("cloud_agent_number"))

    return {
        "designation": designation,
        "alternate_phone_number": alt_phone,
        "cloud_agent_number": cloud_agent,
    }


# =========================================================
# BUILD USER DATA
# =========================================================
def _build_user_data(
    email: str,
    name: str,
    phone: str,
    password: str,
    partner_id: UUID,
    role_id: UUID,
    parent_id: Optional[UUID],
    location_data: LocationData,
    extra_data: Dict[str, Any],
) -> UserData:
    data: Dict[str, Any] = {
        "name": name,
        "email": email,
        "phone_number": phone,
        "password": password,
        "partner_id": partner_id,
        "role_id": role_id,
        "parent_id": parent_id,
        "designation": extra_data["designation"],
        "alternate_phone_number": extra_data["alternate_phone_number"],
        "cloud_agent_number": extra_data["cloud_agent_number"],
    }

    if location_data["country_id"] is not None:
        data["country_id"] = location_data["country_id"]

    if location_data["state_id"] is not None:
        data["state_id"] = location_data["state_id"]

    if location_data["city_id"] is not None:
        data["city_id"] = location_data["city_id"]

    return UserData(**data)


# =========================================================
# MAIN ROW PROCESS
# =========================================================
async def _process_row(
    row: pd.Series,
    auth_service: AuthService,
    partner_id: UUID,
    country_map: Dict[str, Any],
    state_map: Dict[Tuple[str, int], Any],
    city_map: Dict[Tuple[str, int], Any],
    role: Any,
    parent_id: Optional[UUID],
) -> Tuple[RowProcessResult, Optional[int]]:
    email, name, phone, password = _validate_basic_fields(row)

    location_data = _get_location_ids(row, country_map, state_map, city_map)

    extra_data = _get_extra_fields(row)

    user_data = _build_user_data(
        email,
        name,
        phone,
        password,
        partner_id,
        role.id,
        parent_id,
        location_data,
        extra_data,
    )

    try:
        created_user = await auth_service.sing_up(user_data)
        return RowProcessResult.SUCCESS, created_user.id

    except UserCreatedButEmailFailedError as exc:
        # Prefer the user carried on the exception to avoid a race-condition
        # re-fetch; fall back to DB lookup only if the exception doesn't carry one.
        logger.warning("Email failed but user created")
        user = getattr(exc, "user", None)
        return RowProcessResult.EMAIL_FAILED, user.id if user else None


# =========================================================
# HELPER: HANDLE ADMIN SIGNUP
# =========================================================
async def _handle_admin_signup(
    auth_service: AuthService,
    user_repo: UserRepository,
    admin_row: pd.Series,
    partner_id: UUID,
    role_map: Dict[str, Any],
) -> Any:
    try:
        created_admin = await auth_service.sing_up(
            UserData(
                name=admin_row["name"],
                email=_clean_email(admin_row["email"]),
                phone_number=_clean_phone(admin_row["phone_number"]),
                password=_get_password(admin_row.get("password")),
                partner_id=partner_id,
                role_id=role_map["admin"].id,
                parent_id=None,
            )
        )
    except UserCreatedButEmailFailedError as exc:
        logger.warning("Admin created but email failed")
        # Prefer user on exception; only re-fetch if not available
        user = getattr(exc, "user", None)
        if user and user.id:
            return user
        created_admin = await user_repo.get_admin_details_by_partner_id(partner_id)
        if not created_admin:
            raise ValueError("Admin creation failed after email error")
        return created_admin

    if not created_admin or not created_admin.id:
        raise ValueError("Admin creation failed")

    return created_admin


# =========================================================
# CELERY TASK ENTRY
# =========================================================
@celery.task(
    bind=True,
    name="src.components.user.tasks.create_bulk_users",
    queue="user_queue"
)
def create_bulk_users(
    self,
    current_user: CurrentUser,
    file_data_b64: str,
    partner_id: UUID,
    filename: str,
) -> BulkUserResponse:
    task_id: str = self.request.id

    logger.info(
        "Starting bulk user upload task_id=%s partner_id=%s user_id=%s",
        task_id,
        partner_id,
        current_user.get("user_id"),
    )

    async def _run() -> BulkUserResponse:
        try:
            user_id: Optional[UUID] = current_user.get("user_id")
            if user_id is None:
                raise ValueError("user_id is missing")

            try:
                file_data: bytes = base64.b64decode(file_data_b64, validate=True)
            except Exception:
                raise ValueError("Invalid file data (base64 decode failed)")

            return await process_bulk_users(file_data, partner_id, user_id, filename)

        except Exception as exc:
            logger.exception("Task failed: %s", str(exc))
            return {
                "total_success_count": 0,
                "total_failed_count": 0,
                "failed_reasons": [{"reason": str(exc)}],
            }

    return asyncio.run(_run())


async def _resolve_admin(
    df: pd.DataFrame,
    user_repo: UserRepository,
    auth_service: AuthService,
    partner_id: UUID,
    role_map: Dict[str, Any],
) -> Tuple[int, Set[int], Optional[int]]:

    admin_user: Optional[User] = await user_repo.get_admin_details_by_partner_id(partner_id)
    csv_admin_mask = df["role"].fillna("").str.strip().str.lower() == "admin"
    csv_admin_rows = df[csv_admin_mask]
    csv_admin_indexes: List[int] = list(csv_admin_rows.index)

    if not admin_user and csv_admin_rows.empty:
        raise ValueError(
            "Admin is required: please include an admin row in the file or ensure one already exists in the system"
        )

    if admin_user:
        admin_id = getattr(admin_user, "id", None)
        if not admin_id:
            logger.warning(
                "Admin found for partner_id=%s but has invalid id=%s, treating as no admin",
                partner_id, admin_id,
            )
            # Fall through to CSV admin creation
        else:
            skipped: Set[int] = set(csv_admin_indexes)
            logger.info(
                "Admin already in DB (id=%s). Skipping %s CSV admin row(s).",
                admin_id, len(skipped),
            )
            return admin_id, skipped, None

    # No valid admin in DB → need CSV admin row
    if csv_admin_rows.empty:
        raise ValueError("Admin is required: no valid admin in DB and no admin row in CSV")

    first_admin_row: pd.Series = csv_admin_rows.iloc[0]
    first_admin_idx: int = csv_admin_indexes[0]
    skipped_admin_indexes: Set[int] = set(csv_admin_indexes[1:])

    created_admin = await _handle_admin_signup(
        auth_service, user_repo, first_admin_row, partner_id, role_map
    )
    logger.info(
        "Created first admin id=%s. Skipping %s additional admin row(s).",
        created_admin.id, len(skipped_admin_indexes),
    )
    return created_admin.id, skipped_admin_indexes, first_admin_idx


# =========================================================
# PARENT DEPENDENCY GRAPH
# Classifies every processable row's parent reference. No DB calls here —
# `external_lookup` is pre-fetched once for the whole file by the caller.
#
# Every row lands in exactly one bucket:
#   default_admin -> parent cell was blank
#   in_batch      -> parent's email belongs to another row in this file
#   external_db   -> parent's email belongs to a user already in the system
#   self_ref      -> parent's email is the row's own email (invalid)
#   not_found     -> parent's email doesn't match anything, anywhere (invalid)
#
# Split into 3 small pieces (_build_email_index, _classify_parent_ref,
# _build_parent_plan) so each stays well under SonarCloud's Cognitive
# Complexity threshold — same classification logic as a single function,
# just organized so each piece is independently testable.
# =========================================================
def _build_email_index(
    df: pd.DataFrame,
    skipped_admin_indexes: Set[int],
    created_admin_row_index: Optional[int],
) -> Dict[str, int]:
    """Map each processable row's own email -> its row index (first occurrence wins)."""
    email_to_idx: Dict[str, int] = {}
    for idx, row in df.iterrows():
        if idx in skipped_admin_indexes or idx == created_admin_row_index:
            continue
        if row.get("_duplicate_email"):
            continue
        email = row.get("_row_email")
        if email:
            email_to_idx.setdefault(email, idx)
    return email_to_idx


def _classify_parent_ref(
    row: pd.Series,
    admin_id: UUID,
    email_to_idx: Dict[str, int],
    external_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Classify a single row's parent reference into one of 5 buckets. No loops, no I/O."""
    parent_ref = row.get("_parent_ref")
    own_email = row.get("_row_email")

    if not parent_ref:
        return {"parent_id": admin_id, "source": "default_admin", "depends_on_idx": None}

    if own_email and parent_ref == own_email:
        return {"parent_id": None, "source": "self_ref", "depends_on_idx": None}

    if parent_ref in email_to_idx:
        return {"parent_id": None, "source": "in_batch", "depends_on_idx": email_to_idx[parent_ref]}

    existing = external_lookup.get(parent_ref)
    if existing:
        return {"parent_id": existing["id"], "source": "external_db", "depends_on_idx": None}

    return {"parent_id": None, "source": "not_found", "depends_on_idx": None}


def _build_parent_plan(
    df: pd.DataFrame,
    admin_id: UUID,
    skipped_admin_indexes: Set[int],
    created_admin_row_index: Optional[int],
    external_lookup: Dict[str, Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    email_to_idx = _build_email_index(df, skipped_admin_indexes, created_admin_row_index)

    plan: Dict[int, Dict[str, Any]] = {}
    for idx, row in df.iterrows():
        if idx in skipped_admin_indexes or idx == created_admin_row_index:
            continue
        if row.get("_duplicate_email"):
            continue
        plan[idx] = _classify_parent_ref(row, admin_id, email_to_idx, external_lookup)

    return plan


# =========================================================
# WAVE PROCESSOR
# Kahn's algorithm: process every row whose parent is already known,
# record its new id, then whatever depends on it becomes processable next.
# This is what makes chains like U2->U1, U3->U2, U4->U3 resolve correctly
# no matter what order they appear in the uploaded file.
# =========================================================
async def _resolve_external_parents(
    df: pd.DataFrame,
    user_repo: UserRepository,
    skipped_admin_indexes: Set[int],
    created_admin_row_index: Optional[int],
) -> Dict[str, Dict[str, Any]]:
    """
    Batch-fetch DB info for every parent-ref that ISN'T another row in this
    file. Admin/duplicate rows are excluded here too, for the same reason
    _build_email_index excludes them — otherwise a parent reference
    pointing at one of them would be wrongly treated as "in-batch but
    unmatched" instead of falling through to this DB lookup, where both
    are already committed and findable by the time this function runs.
    """
    in_batch_emails: Set[str] = {
        row["_row_email"]
        for idx, row in df.iterrows()
        if row.get("_row_email")
        and not row.get("_duplicate_email")
        and idx not in skipped_admin_indexes
        and idx != created_admin_row_index
    }
    external_refs: Set[str] = {
        row["_parent_ref"]
        for _, row in df.iterrows()
        if row.get("_parent_ref") and row["_parent_ref"] not in in_batch_emails
    }
    return await user_repo.get_users_id_hierarchy_by_emails(list(external_refs))


def _compute_immediate_failures(
    plan: Dict[int, Dict[str, Any]],
    df: pd.DataFrame,
) -> Dict[int, str]:
    """Rows that can never succeed, known without running any creation logic."""
    immediate_failures: Dict[int, str] = {}
    for idx, entry in plan.items():
        if entry["source"] == "self_ref":
            immediate_failures[idx] = ValidationMsg.PARENT_SELF_REF
        elif entry["source"] == "not_found":
            ref = df.loc[idx, "_parent_ref"]
            immediate_failures[idx] = ValidationMsg.PARENT_NOT_FOUND.format(email=ref)
    return immediate_failures


def _build_dependency_graph(
    plan: Dict[int, Dict[str, Any]],
) -> Tuple[Dict[int, List[int]], Dict[int, int]]:
    """
    Kahn's-algorithm graph over in-batch parent dependencies.

    NOTE: `children` intentionally stays a dict comprehension, NOT
    dict.fromkeys(plan, []) — fromkeys would make every value point at the
    SAME list object, so appending a child for one row would silently
    "leak" into every other row's list too. `in_degree` is safe to build
    with fromkeys since 0 is immutable.
    """
    children: Dict[int, List[int]] = {idx: [] for idx in plan}
    in_degree: Dict[int, int] = dict.fromkeys(plan, 0)
    for idx, entry in plan.items():
        if entry["source"] == "in_batch":
            parent_idx = entry["depends_on_idx"]
            in_degree[idx] += 1
            children.setdefault(parent_idx, []).append(idx)
    return children, in_degree


def _cascade_failures(
    start_indices: List[int],
    children: Dict[int, List[int]],
    failed_idx: Set[int],
    immediate_failures: Dict[int, str],
) -> None:
    """
    Propagate a failure down every descendant, transitively. Used both for
    failures known before processing starts (self-ref/not-found) and for
    failures discovered mid-wave (a row's creation actually raised) —
    without this, a descendant of a failed row would never get visited
    and would be wrongly reported as a circular reference instead of
    "your ancestor failed to be created".
    """
    queue: List[int] = list(start_indices)
    while queue:
        parent_idx = queue.pop()
        for child_idx in children.get(parent_idx, []):
            if child_idx not in failed_idx:
                failed_idx.add(child_idx)
                immediate_failures.setdefault(child_idx, ValidationMsg.PARENT_ROW_FAILED)
                queue.append(child_idx)


# ---------------------------------------------------------
# _run_waves helpers
#
# Pulled out of _run_waves (which previously nested two closures plus a
# multi-branch loop body inline) purely to bring its Cognitive Complexity
# under SonarCloud's threshold. No behavior changed unless noted: each
# helper below does what the corresponding inline block did before, and
# all of them still mutate the SAME shared dicts/sets (`failed_idx`,
# `in_degree`, `resolved_id_by_email`, etc.) that _run_waves passes them.
# ---------------------------------------------------------

def _initial_ready_queue(
    plan: Dict[int, Dict[str, Any]],
    failed_idx: Set[int],
    in_degree: Dict[int, int],
) -> List[int]:
    """Every row with no unresolved in-batch parent is processable in wave 1."""
    return [
        idx for idx in plan if idx not in failed_idx and in_degree.get(idx, 0) == 0
    ]


def _resolve_parent_id_for_row(
    idx: int,
    plan: Dict[int, Dict[str, Any]],
    df: pd.DataFrame,
    resolved_id_by_email: Dict[str, int],
) -> Optional[int]:
    """
    default_admin/external_db rows already carry their final parent_id in
    the plan. in_batch rows don't -- their parent only got a real id once
    an earlier wave created it, so look that up by the parent's email.
    """
    entry = plan[idx]
    if entry["source"] == "in_batch":
        parent_email = df.loc[entry["depends_on_idx"], "_row_email"]
        return resolved_id_by_email.get(parent_email)
    return entry["parent_id"]


def _is_duplicate_user_error(exc: Exception) -> bool:
    """
    True only when a row's creation failed specifically because that
    user already exists (matched by email or phone) -- as opposed to
    any other validation or DB error. Used so an "already exists"
    outcome for a PARENT row doesn't wrongly cascade-fail every child
    row that names them as parent: the parent is a perfectly valid,
    resolvable existing user, it just wasn't newly created here.
    """
    msg = str(exc)
    return (
        AuthExceptionMsg.EMAIL_EXIST in msg
        or AuthExceptionMsg.PHONE_NUMBER_EXIST in msg
    )


async def _lookup_existing_user_id(
    row: pd.Series,
    user_repo: UserRepository,
) -> Optional[int]:
    """
    Called only after a "user already exists" failure. Resolves that
    user's real id by their own email so rows elsewhere in this file
    that name them as `parent` get a real parent_id instead of being
    cascade-failed for something that isn't their fault.
    """
    email = row.get("_row_email")
    if not email:
        return None
    found = await user_repo.get_users_id_hierarchy_by_emails([email])
    entry = found.get(email)
    return entry["id"] if entry else None


async def _create_row(
    idx: int,
    df: pd.DataFrame,
    plan: Dict[int, Dict[str, Any]],
    resolved_id_by_email: Dict[str, int],
    role_map: Dict[str, Any],
    auth_service: AuthService,
    partner_id: UUID,
    country_map: Dict[str, Any],
    state_map: Dict[Tuple[str, int], Any],
    city_map: Dict[Tuple[str, int], Any],
    sem: asyncio.Semaphore,
    user_repo: UserRepository,
) -> RowResult:
    """
    Validate + create a single row. Any exception -- role lookup, field
    validation, or the signup call itself -- is caught here and turned
    into a failed RowResult instead of propagating, so one bad row never
    aborts the rest of the wave.

    Special case: if creation failed only because the user already
    exists (matched by email/phone), we still resolve their real id
    from the DB via _lookup_existing_user_id. The row itself is still
    reported as a failure (it created nothing new here), but rows
    elsewhere in the file that name this email as their parent are NOT
    cascade-failed anymore -- see _apply_wave_result.
    """
    row = df.loc[idx]
    try:
        role = _get_role(row, role_map)
        parent_id = _resolve_parent_id_for_row(idx, plan, df, resolved_id_by_email)
        row_out = row.to_dict()
        row_out["_resolved_parent_id"] = parent_id
        async with sem:
            status, user_id = await _process_row(
                row, auth_service, partner_id,
                country_map, state_map, city_map, role, parent_id,
            )
            return idx, row_out, status, user_id, None
    except Exception as exc:
        row_out = row.to_dict()
        existing_id: Optional[UUID] = None
        if _is_duplicate_user_error(exc):
            existing_id = await _lookup_existing_user_id(row, user_repo)
            if existing_id is not None:
                logger.info(
                    "Row %s: user already exists (id=%s) -- dependent rows "
                    "will use this id instead of being failed",
                    idx + 1, existing_id,
                )
        return idx, row_out, None, existing_id, exc


def _apply_wave_result(
    result: RowResult,
    processed: Set[int],
    all_results: List[RowResult],
    resolved_id_by_email: Dict[str, int],
    children: Dict[int, List[int]],
    in_degree: Dict[int, int],
    failed_idx: Set[int],
    ready_next: List[int],
) -> Optional[int]:
    """
    Folds one row's outcome into the running wave state (in place).

    On success, records the new id and unlocks any children whose
    in-degree just hit zero into `ready_next`.

    On failure, returns the row's index so the caller can cascade the
    failure through its descendants -- UNLESS an existing user's id was
    still resolved for this row (see _create_row's duplicate-user case),
    in which case dependents are unlocked normally using that id instead
    of being wrongly cascade-failed for their parent's pre-existing
    account.
    """
    idx, row_dict, _status, user_id, exc = result
    processed.add(idx)
    all_results.append(result)

    row_email = row_dict.get("_row_email")
    if user_id is not None and row_email:
        resolved_id_by_email[row_email] = user_id

    if exc is not None and user_id is None:
        return idx

    for child_idx in children.get(idx, []):
        in_degree[child_idx] -= 1
        if child_idx not in failed_idx and in_degree[child_idx] == 0:
            ready_next.append(child_idx)

    return None


def _mark_cycles_as_failed(
    plan: Dict[int, Dict[str, Any]],
    processed: Set[int],
    failed_idx: Set[int],
    immediate_failures: Dict[int, str],
) -> None:
    """Anything never visited by a wave is a genuine cycle (A -> B -> A ...)."""
    for idx in plan:
        if idx not in processed and idx not in failed_idx:
            immediate_failures[idx] = ValidationMsg.PARENT_CYCLE
            failed_idx.add(idx)


async def _run_waves(
    plan: Dict[int, Dict[str, Any]],
    df: pd.DataFrame,
    children: Dict[int, List[int]],
    in_degree: Dict[int, int],
    failed_idx: Set[int],
    immediate_failures: Dict[int, str],
    auth_service: AuthService,
    partner_id: UUID,
    country_map: Dict[str, Any],
    state_map: Dict[Tuple[str, int], Any],
    city_map: Dict[Tuple[str, int], Any],
    role_map: Dict[str, Any],
    user_repo: UserRepository,
) -> List[RowResult]:
    """
    Kahn's algorithm execution: process every row whose parent is already
    known/created, record its new id, then whatever depends on it becomes
    processable in the next wave.

    Orchestrator only -- see _create_row / _apply_wave_result /
    _mark_cycles_as_failed above. Same logic as before, just split up so
    this stays well under SonarCloud's Cognitive Complexity threshold
    (each piece is also independently testable, same as the rest of this
    file's helpers).
    """
    resolved_id_by_email: Dict[str, int] = {}
    processed: Set[int] = set()
    ready: List[int] = _initial_ready_queue(plan, failed_idx, in_degree)

    sem = asyncio.Semaphore(10)
    all_results: List[RowResult] = []

    while ready:
        wave, ready = ready, []
        wave_results = await asyncio.gather(*(
            _create_row(
                idx, df, plan, resolved_id_by_email, role_map,
                auth_service, partner_id, country_map, state_map, city_map, sem,
                user_repo,
            )
            for idx in wave
        ))

        newly_failed: List[int] = []
        for result in wave_results:
            failed_row_idx = _apply_wave_result(
                result, processed, all_results, resolved_id_by_email,
                children, in_degree, failed_idx, ready,
            )
            if failed_row_idx is not None:
                newly_failed.append(failed_row_idx)

        # Cascade every failure from this wave through its FULL descendant
        # chain before starting the next wave, so multi-level chains fail
        # correctly all the way down instead of only one hop. Rows whose
        # id was still resolved (existing-user case) never reach here --
        # _apply_wave_result only returns an idx for genuine failures.
        _cascade_failures(newly_failed, children, failed_idx, immediate_failures)

    _mark_cycles_as_failed(plan, processed, failed_idx, immediate_failures)

    return all_results


def _merge_bookkeeping_results(
    df: pd.DataFrame,
    all_results: List[RowResult],
    immediate_failures: Dict[int, str],
    skipped_admin_indexes: Set[int],
    created_admin_row_index: Optional[int],
    admin_id: UUID,
) -> Dict[int, RowResult]:
    """
    Rows fully excluded from the parent-plan (duplicate emails, admin
    bookkeeping) still need a result entry so the output file and totals
    stay complete.
    """
    result_map: Dict[int, RowResult] = {r[0]: r for r in all_results}
    for idx, reason in immediate_failures.items():
        if idx not in result_map:
            result_map[idx] = (idx, df.loc[idx].to_dict(), None, None, Exception(reason))

    bookkeeping_results: Dict[int, RowResult] = {}
    for idx, row in df.iterrows():
        if row.get("_duplicate_email"):
            bookkeeping_results[idx] = (
                idx, row.to_dict(), None, None,
                Exception("This email already appears earlier in the file, so this row was skipped."),
            )
        elif idx in skipped_admin_indexes:
            reason = (
                "Only the first Admin row in the file is used; this extra Admin row was skipped."
                if created_admin_row_index is not None
                else "An Admin already exists for this account, so this row was skipped."
            )
            bookkeeping_results[idx] = (idx, row.to_dict(), None, None, Exception(reason))
        elif idx == created_admin_row_index:
            bookkeeping_results[idx] = (
                idx, row.to_dict(), RowProcessResult.SUCCESS, admin_id, None,
            )

    return {**bookkeeping_results, **result_map}


async def _process_rows_with_parent_resolution(
    df: pd.DataFrame,
    auth_service: AuthService,
    user_repo: UserRepository,
    partner_id: UUID,
    country_map: Dict[str, Any],
    state_map: Dict[Tuple[str, int], Any],
    city_map: Dict[Tuple[str, int], Any],
    role_map: Dict[str, Any],
    admin_id: UUID,
    skipped_admin_indexes: Set[int],
    created_admin_row_index: Optional[int],
) -> Tuple[List[Dict[str, Any]], int, int, List[Dict[str, Any]]]:
    """
    Orchestrator only — each step below is independently testable, which
    is what actually gets coverage close to 100% (a single giant function
    never will, no matter how many tests you throw at it).
    """
    external_lookup = await _resolve_external_parents(
        df, user_repo, skipped_admin_indexes, created_admin_row_index
    )
    plan = _build_parent_plan(
        df, admin_id, skipped_admin_indexes, created_admin_row_index, external_lookup
    )

    immediate_failures = _compute_immediate_failures(plan, df)
    children, in_degree = _build_dependency_graph(plan)

    failed_idx: Set[int] = set(immediate_failures.keys())
    _cascade_failures(list(failed_idx), children, failed_idx, immediate_failures)

    all_results = await _run_waves(
        plan, df, children, in_degree, failed_idx, immediate_failures,
        auth_service, partner_id, country_map, state_map, city_map, role_map,
        user_repo,
    )

    result_map = _merge_bookkeeping_results(
        df, all_results, immediate_failures,
        skipped_admin_indexes, created_admin_row_index, admin_id,
    )

    return _collate_results(result_map)


def _collate_results(
    result_map: Dict[int, RowResult],
) -> Tuple[List[Dict[str, Any]], int, int, List[Dict[str, Any]]]:
    success_count = 0
    failed_count = 0
    rows_result: List[Dict[str, Any]] = []
    failed_reasons: List[Dict[str, Any]] = []

    for idx in sorted(result_map.keys()):
        _, row_dict, status, user_id, exc = result_map[idx]
        resolved_parent_id = row_dict.pop("_resolved_parent_id", None)
        for internal_col in ("_duplicate_email", "_row_email", "_parent_ref"):
            row_dict.pop(internal_col, None)

        if exc is not None:
            logger.warning("Row %s failed error=%s", idx + 1, str(exc))
            # If we still resolved the existing user's real id (the
            # "already exists" case), surface it in the failed row's
            # output too, along with a reason that makes clear their
            # dependents were NOT failed because of this.
            if user_id is not None:
                reason = (
                    "{} (Other rows in this file that list this user as "
                    "their parent were still processed normally, using "
                    "the existing user's id={}.)"
                ).format(str(exc), user_id)
            else:
                reason = str(exc)
            new_row = row_dict.copy()
            new_row.update({
                "user_id": user_id,
                "parent_id": resolved_parent_id,
                "status": "Failure",
                "reason": reason,
            })
            rows_result.append(new_row)
            failed_reasons.append({
                "email": row_dict.get("email"),
                "name": row_dict.get("name"),
                "reason": reason,
            })
            failed_count += 1
            continue

        reason = (
            "User created, but the welcome email could not be sent."
            if status == RowProcessResult.EMAIL_FAILED else ""
        )
        new_row = row_dict.copy()
        new_row.update({
            "user_id": user_id,
            "parent_id": resolved_parent_id,
            "status": "Success",
            "reason": reason,
        })
        rows_result.append(new_row)
        success_count += 1

    return rows_result, success_count, failed_count, failed_reasons


# =========================================================
# MAIN PROCESS FUNCTION
# =========================================================
async def process_bulk_users(
    file_data: bytes,
    partner_id: UUID,
    user_id: UUID,
    filename: str,
) -> BulkUserResponse:

    container = celery.container

    auth_service: AuthService = await container.auth_service.async_()
    auth_repo: AuthRepository = container.auth_repository()
    location_repo: LocationRepository = container.location_repository()
    user_repo: UserRepository = await container.console_service()

    df = _read_file(file_data, filename)
    logger.info("File parsed successfully total_rows=%s", len(df))

    # =========================================================
    # BUILD LOCATION MAPS
    # Normalised via _get_id / _get_name so the maps work
    # regardless of whether each repo returns dicts or ORM objects.
    # =========================================================
    countries = await location_repo.get_all_countries(None)
    country_map: Dict[str, Any] = {
        _get_name(c).lower(): c for c in countries if _get_name(c)
    }

    all_states = await location_repo.get_all_states()
    state_map: Dict[Tuple[str, int], Any] = {
        (_get_name(s).lower(), _get_country_id(s)): s
        for s in all_states
        if _get_name(s) and _get_country_id(s) is not None
    }

    all_cities = await location_repo.get_all_cities()
    city_map: Dict[Tuple[str, int], Any] = {
        (_get_name(c).lower(), _get_state_id(c)): c
        for c in all_cities
        if _get_name(c) and _get_state_id(c) is not None
    }

    roles = await auth_repo.get_all_role(
        is_internal_partner=False
    )
    role_map: Dict[str, Any] = {r.name.lower(): r for r in roles}

    admin_id, skipped_admin_indexes, created_admin_row_index = await _resolve_admin(
        df, user_repo, auth_service, partner_id, role_map
    )

    rows_result, success_count, failed_count, failed_reasons = (
        await _process_rows_with_parent_resolution(
            df,
            auth_service,
            user_repo,
            partner_id,
            country_map,
            state_map,
            city_map,
            role_map,
            admin_id,
            skipped_admin_indexes,
            created_admin_row_index,
        )
    )

    # =========================================================
    # RESULT CSV (kept in-memory; result-file download retired with storage)
    # =========================================================
    csv_bytes: bytes = _convert_result_to_bytes(rows_result)

    logger.info(
        "Bulk user upload completed success=%s failed=%s",
        success_count, failed_count,
    )

    return {
        "total_success_count": success_count,
        "total_failed_count": failed_count,
        "failed_reasons": failed_reasons,
    }


# =========================================================
# EXTERNAL TASK
# =========================================================
@celery.task(
    name="process_api_log",
    queue="common_notifications_queue"
)
def process_api_log(data: Dict[str, Any]) -> Dict[str, str]:
    logger.info("Received external API log task, ignoring: %s", data)
    return {"status": "ignored"}