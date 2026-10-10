from enum import Enum


class PartnerResponseData:
    PARTNER_EXIST: str = (
        "Partner with this name already exists or Partner is deactivated"
    )
    PUBLISHER_EXIST: str = (
        "Publisher with this name already exists or Publisher is deactivated"
    )
    DELETE_PARTNER: str = "Partner deleted successfully."
    CHANGE_PARTNER_STATUS_VALIDATION: str = (
        "Only internal team members can change the active status of partner"
    )


class PartnerStatus:
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BLACKLISTED = "BLACKLISTED"
    DISABLED = "DISABLED"

    @classmethod
    def choices(cls):
        return [cls.ACTIVE, cls.SUSPENDED, cls.BLACKLISTED, cls.DISABLED]


class BillingCycle:
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class PaginationConstants:
    OFFSET: int = 1
    LIMIT: int = 10
    LIMIT_MAX: int = 500


class DashboardFilters(Enum):
    PARTNERS_USING_MAGLO = "partners_using_maglo"
    PARTNERS_USING_TALKO = "partners_using_talko"
    PARTNERS_USING_BABBLER = "partners_using_babbler"
    PARTNERS_GT_FIFTY_LICENSES = "partners_gt_fifty_licenses"
    PARTNERS_LAST_SEVEN_DAYS = "partners_last_seven_days"


class TrialPartnerConstant:
    TRIAL_PERIOD_DAYS: int = 7
    ALLOWED_USER: int = 3


class TrialPartnerExceptionMessage:
    PARTNER_EXISTS: str = "Partner already exists with provided details"
    USER_EXISTS: str = "User already exists with same email or phone number"
