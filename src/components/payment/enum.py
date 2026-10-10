class EntityNameEnum:
    """Represents what the payment is made for."""

    BABBLER_WALLET = "BABBLER_WALLET"
    BABBLER_PLATFORM_FEE = "BABBLER_PLATFORM_FEE"
    MAGLO_DIDS = "MAGLO_DIDS"
    PLAN = "PLAN"


class PaymentClientEnum:
    """Supported payment gateways."""

    RAZORPAY = "RAZORPAY"


class PaymentStatusEnum:
    """Status of payment transaction."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentBillingCycle:
    """Partner's billing cycle"""

    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"
