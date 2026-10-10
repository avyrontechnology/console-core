from typing import List, Tuple

DEV_ERROR_MAIL_RECIPENTS: List[str] = ["sahil.jha@makunaiglobal.ai"]
QA_ERROR_MAIL_RECIPENTS: List[str] = ["sahil.jha@makunaiglobal.ai"]
PROD_ERROR_MAIL_RECIPENTS: List[str] = [
    "abhinay.singh@makunaiglobal.ai",
    "aditya.tiwari@makunaiglobal.ai",
    "aditya@makunaiglobal.ai",
    "afzal.ahmad@makunaiglobal.ai",
    "anmol.tanwar@makunaiglobal.ai",
    "naved.ahemd@makunaiglobal.ai",
    "roshan.singh@makunaiglobal.ai",
    "sahil.jha@makunaiglobal.ai",
    "santosh.mishra@makunaiglobal.ai",
    "vinayakp.tripathi@makunaiglobal.ai",
    "shashank@makunaiglobal.ai",
]

OPTIONAL_AUTH_PATHS: Tuple[str, ...] = (
    "get-plans",
    "billing-details",
    "get-modules",
)


class Product:
    MAGLO = "maglo"
    BABBLER = "babbler"
    TALKO = "talko"
    CONSOLE = "console"

    VALID_VALUES = frozenset({MAGLO, BABBLER, TALKO, CONSOLE})


class Platform:
    WEB = "web"
    APP = "app"

    VALID_VALUES = frozenset({WEB, APP})


class ClientType:
    UNKNOWN = "unknown"

    VALID_VALUES: frozenset[str] = frozenset(
        f"{p}-{pl}" for p in Product.VALID_VALUES for pl in Platform.VALID_VALUES
    )