from src.components.payment.enum import PaymentStatusEnum

STATUS_MAPPING = {
    "success": PaymentStatusEnum.SUCCESS,
    "captured": PaymentStatusEnum.SUCCESS,
    "paid": PaymentStatusEnum.SUCCESS,
    "authorized": PaymentStatusEnum.PENDING,
    "created": PaymentStatusEnum.PENDING,
    "failed": PaymentStatusEnum.FAILED,
    "refunded": PaymentStatusEnum.REFUNDED,
}

AMOUNT_ADDED_IN_WALLET: str = "Amount Added in Wallet"

DAYS_PER_MONTH: int = 30

MAX_PARTNER_ID_INT32: int = 2_147_483_647
MAX_PARTNER_IDS_PER_REQUEST: int = 100


class OrderSource:
    BABBLER: str = "babbler"
    CONSOLE: str = "console"
    MAGLO: str = "maglo"
    MAGLO_APP: str = "maglo_app"
    OBOTAAI_WEBSITE: str = "obotaai_website"


class OrderType:
    FRESH: str = "FRESH"
    RENEWAL: str = "RENEWAL"
    UPGRADE: str = "UPGRADE"
    DOWNGRADE: str = "DOWNGRADE"


class PaymentMethod:
    GATEWAY: str = "GATEWAY"
    DIRECT: str = "DIRECT"


class ServiceSubscriptionStatus:
    ACTIVE = "active"
    GRACE = "grace"
    SUSPENDED = "suspended"
    PENDING_ACTIVATION = "pending_activation"
    CANCELED = "canceled"
    PAYMENT_FAILED = "payment_failed"


class OrderEmailConstants:
    LIST_OF_RECIEVERS = [
        'sachmann.singh@makunaiglobal.ai',
    ]

    SUBJECT = 'Daily Orders Report'


MILLISECONDS_IN_DAY = 24 * 60 * 60 * 1000