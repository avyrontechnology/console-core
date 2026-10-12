from decimal import Decimal
from enum import Enum

from reportlab.lib import colors


class TransactionType(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    FREEZE = "FREEZE"
    UNFREEZE = "UNFREEZE"


class ServiceName(str, Enum):
    TALKO = "Talko"
    OBOTAAI = "Obotaai"


class Currency:
    INDIA = "INR"


ALL_CURRENCIES = currencies = [
    value
    for key, value in Currency.__dict__.items()
    if not key.startswith("__")
]


STATEMENT_TITLE = "Wallet Transaction Statement"

TABLE_HEADERS = [
    "Date & Time",
    "Service Name",
    "Transaction Type",
    "Description",
    "Debit",
    "Credit",
    "Balance",
    "Status",
]

TABLE_COLUMN_WIDTHS = [
    1.4 * 72,
    1.2 * 72,
    1.4 * 72,
    3.5 * 72,
    0.8 * 72,
    0.8 * 72,
    0.9 * 72,
]

# Color constants
HEADER_BG_COLOR = colors.HexColor("#1740E8")
HEADER_TEXT_COLOR = colors.white
GRID_COLOR = colors.grey

MAX_WALLET_NUMERIC = Decimal("9999999999.99")


class PartnerTimeZone:
    ASIA_KOLKATA: str = "Asia/Kolkata"
