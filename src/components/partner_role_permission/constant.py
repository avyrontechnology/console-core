class ExceptionMsg:
    PARTNER_NOT_FOUND = "Partner does not exist or is inactive."
    PERMISSION_NOT_FOUND = "Permission does not exist or is inactive."
    ROLE_NOT_FOUND = "Role does not exist or is inactive."
    DEFAULT_ROLE_PERMISSION_NOT_FOUND = (
        "Default role permission mapping does not exist."
    )
    IS_CUSTOM_PERMISSION_FALSE = (
        "Can't create partner role permission with false custom role permission value."
    )
    PARTNER_PERMISSION_MATRIX_ERROR= "invalid partner id or config key is not set for prtner id: {}"
    CANT_CREATE_IF_ONE_IS_INTERNAL = "both partner and role must be internal or external."


class SuccessResponseMsg:
    PARTNER_PERMISSION_DELETE = "Partner role permission deleted successfully."
