"""Plan-related constants."""


class PlanCustomLimitKeys:
    class Maglo:
        SERVICE_BOARDS = "SERVICE_BOARDS"

    class Console:
        ACTIVE_USERS = "ACTIVE_USERS"


class Platform:
    OBOTAAI: str = "obotaai"
    BABBLER: str = "babbler"
    CONSOLE: str = "console"
    MAGLO: str = "maglo"


class PlanType:
    STANDARD = "STANDARD"
    WALLET = "WALLET"
