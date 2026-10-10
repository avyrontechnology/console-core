class Keys:
    ENLIST_AGENTS: str = "ENLIST_AGENTS_PARTNER:{}"
    TOKEN: str = "PARTNER:{}_TOKEN:{}"
    COUNTRIES: str = "COUNTRIES"
    STATES: str = "STATES_COUNTRY:{}"
    CITIES: str = "CITIES_STATE:{}"
    PARTNER_CONFIG: str = "PARTNER_CONFIG_KEY:{}_PARTNER:{}"
    ALL_PARTNER_CONFIGS: str = "PARTNER_CONFIG_PARTNER:{}"
    HOME_PAGE: str = "HOME_PAGE_PARTNER:{}_USER:{}"
    ALL_USER_CONFIGS: str = "USER_CONFIG_USER:{}"
    USER_CONFIG: str = "USER_CONFIG_KEY:{}_USER:{}"
    GRPC_GET_USER_CHILD_DETAILS: str = "gRPC_GET_USER_CHILD_DETAILS_PARTNER:{}_USER:{}"
    GRPC_GET_USER_DETAILS: str = "gRPC_GET_USER_DETAILS_PARTNER:{}_USER:{}"
    GRPC_GET_ALL_PUBLISHERS: str = "gRPC_GET_ALL_PUBLISHERS"
    GRPC_GET_PUBLISHER_DATA: str = "gRPC_GET_PUBLISHER_DATA:{}"
    GRPC_GET_PARTNER_DETAILS: str = "gRPC_GET_PUBLISHER_DETAILS:{}"
    GRPC_GET_USER_ROLE: str = "gRPC_GET_USER_ROLE:{}"
    GRPC_GET_USER_PERMISSIONS: str = "gRPC_GET_USER_PERMISSIONS:{}"
    PARTNER_API_KEY: str = "PARTNER_API_KEY:{}"
    GRPC_GET_USER_CHILD_HIERARCHY: str = "gRPC_GET_USER_CHILD_HIERARCHY_PARTNER:{}_USER:{}"
    GRPC_GET_USER_TEAMS: str = "gRPC_GET_USER_TEAMS_PARTNER:{}_USER:{}"
    GRPC_GET_PARTNER_TEAMS: str = "gRPC_GET_PARTNER_TEAMS_PARTNER:{}"
    # Team-scoped effective role + permissions maglo caches per (user, team).
    # Byte-identical to the maglo-service key template so console can bust it.
    GRPC_GET_USER_TEAM_ROLE: str = "gRPC_GET_USER_TEAM_ROLE_USER:{}_TEAM:{}"
    # Configured permission slugs for a role, maglo caches per role_id.
    # Byte-identical to the maglo-service key template so console can bust it.
    GRPC_GET_ROLE_PERMISSIONS: str = "gRPC_GET_ROLE_PERMISSIONS_ROLE:{}"
    DB_CONFIG_KEY_PARTNER: str = "DB_CONFIG_KEY_PARTNER:{}"


class TTL:
    ONE_WEEK: int = 7 * 24 * 60 * 60
