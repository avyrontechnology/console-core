"""Grace Period constants."""


class GraceStatus:
    ACTIVE: str = "ACTIVE"
    EXPIRED: str = "EXPIRED"
    SETTLED: str = "SETTLED"


GRACE_MS_PER_DAY: int = 86_400_000  # milliseconds in one day
