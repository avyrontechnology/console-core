from pydantic import BaseModel, EmailStr

class Contrasts:
    class UserData(BaseModel):
        name: str
        password: str
        email: EmailStr
        phone_number: str
        is_active: bool
  
class UserResponseMsg:
    DELETE_USER: str = "User deleted successfully."
    EMAIL_ALREADY_EXISTS: str = "Provided email already exists."
    USER_NOT_FOUND: str = "User not found"
    PHONE_NUMBER_ALREADY_EXISTS: str = "Provided phone number already exists for other user."
    OTP_SENT: str = "OTP has been sent on email"
    ACCOUNT_DELETED: str = "Your account has been deleted successfully."

class UserLogMsg:
    USER_NOT_FOUND: str = "user not found"
    ALREADY_IN_STATUS: str = "User is already {}"

class PaginationConstants:
    offset: int = 1
    limit: int = 10
    LIMIT_MAX: int = 500


class UserRoles:
    ADMIN = "admin"
    MAINTAINER = "maintainer"

class UserWalkthroughAttribtes:
    WALKTHROUGH_TIME_PERIOD: int = 259200000

OBOTAAI_PARTNER_ID = 12

class ValidationMsg:
    EMAIL_REQUIRED: str = "Email is required"
    NAME_REQUIRED: str = "Name is required"
    PHONE_REQUIRED: str = "Phone number is required"
    INVALID_PHONE: str = "Invalid phone number — only 10-digit Indian numbers are supported"
    ROLE_REQUIRED: str = "Role ID is required"
    PARENT_REQUIRED: str = "Parent ID is required"
    INVALID_EMAIL = "Invalid email format"
    MANDATORY_COLUMNS_MISSING = "Missing required column: {column}"
    ONLY_CSV_SUPPORTED = "Only CSV or Excel (.xlsx) files are supported."
    NO_USER_RECORDS = "No user records found. Please add user details to upload."
    INVALID_CSV_FORMAT = "Only CSV and XLSX files are supported."

    # --- Bulk-upload PARENT column messages ---
    # 'parent' holds the parent user's EMAIL — the only field guaranteed
    # unique. These messages are shown directly in the result file's
    # "reason" column, so they're written for the person uploading the
    # file, not for a developer reading logs.
    PARENT_NOT_FOUND = (
        "No user was found with parent email '{email}'. "
        "Check the spelling, or add that user to the file first."
    )
    PARENT_SELF_REF = (
        "This user's parent cannot be the user's own email address."
    )
    PARENT_CYCLE = (
        "This user and their parent depend on each other in a loop "
        "(A is B's parent and B is A's parent). Fix one side of the chain."
    )
    PARENT_ROW_FAILED = (
        "This user's parent could not be created, so this user could not be created either."
    )


class FileContent:
    FILE_CONTENT_TYPE = [
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-excel",  # some browsers send this for .xlsx too
    ]

    CSV_TEXT = "text/csv"
    XLSX_TEXT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
class TextPrompt:
    FILE_PROCESSED_SUCCESSFULLY: str = "File Processed Successfully"
    FILE_PROCESSED_UNSUCCESSFULLY: str = "File Processed Unsuccessfully"
    FILE_EMPTY: str = "File is empty"
    
class UserDefaults:
    PASSWORD: str = "Temp@123"
    
from enum import Enum

class RowProcessResult(str, Enum):
    SUCCESS = "success"
    EMAIL_FAILED = "email_failed"
    
class FileNames:
    USER_REFERENCE_FILE = "user_bulk_upload_reference.csv"
    
class BulkUploadColumns:
    NAME = "name"
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    ROLE = "role"
    PASSWORD = "password"
    DESIGNATION = "designation"
    COUNTRY = "country"
    STATE = "state"
    CITY = "city"
    PARENT = "parent"

    TEAM = "team"
    CUSTOM_ROLE = "custom_role"

    MANDATORY = [
        NAME,
        EMAIL,
        PHONE_NUMBER,
        ROLE,
    ]

    OPTIONAL = [
        PASSWORD,
        DESIGNATION,
        COUNTRY,
        STATE,
        CITY,
        PARENT,
    ]

    CONDITIONAL = {
        TEAM: "is_teams_enabled",
        CUSTOM_ROLE: "is_partner_custom_roles_enabled",
    }