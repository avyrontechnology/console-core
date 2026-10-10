class ApiKeyResponseMessage:
    API_KEY_IN_ACTIVIATED: str = "API key inactivated successfully."

class ExceptionMessages:
    PARTNER_OR_USER_NOT_PROVIDED: str = "Partner or current user details not provided"
    PARTNER_ID_REQUIRED_FOR_SYSTEM_CALL: str = "partner_id is required when current_user is not provided"
    INVALID_SCOPES: str = "Unknown permission slug(s) in scopes: {}"
    INVALID_USER_CONTEXT: str = "user_context must be a JSON object"
    USER_CONTEXT_ONLY_USER_ID: str = (
        "user_context may only contain 'user_id'; unexpected key(s): {}"
    )
    INVALID_USER_ID_IN_CONTEXT: str = "user_context.user_id must be an integer"
    USER_CONTEXT_USER_NOT_FOUND: str = (
        "user_context.user_id {} is not a valid user for this partner"
    )

