class BuilderExceptionMessage:
    FIELD_NOT_EXIST: str = "Field '{}' does not exist in model {}"
    INVALID_OPERATOR_FORMAT: str = "Invalid format for '{}' operator with value '{}'"
    UNSUPPORTED_OPERATOR: str = "Unsupported operator: {}"
    UNSUPPORTED_OPERATOR_FOR_INT: str = (
        "Operator '{}' is not supported for Integer fields."
    )
    INVALID_TIME_STAMP: str = (
        "Invalid timestamp format. Expected format is in milliseconds."
    )
    UNSUPPORTED_DATE_OPERATOR: str = (
        "Operator '{}' is not supported for date field '{}'. "
        "Supported operators are: =, !=, <, >, <=, >=, BETWEEN."
    )
    INVALID_DATE_VALUE: str = (
        "Invalid date value '{}' for field '{}'. Expected epoch milliseconds or "
        "one of the formats: YYYY-MM-DD, DD-MMM-YYYY."
    )
    INVALID_RANGE_VALUE: str = (
        "Operator '{}' expects exactly two values for field '{}', got {}."
    )
    INVALID_BOOLEAN_VALUE: str = "Cannot convert '{}' (type: {}) to boolean"


class FilterCriteriaMessage:
    PARALLEL_LENGTH_MISMATCH: str = (
        "filter_by_fields, operators and values must have the same number of "
        "entries (got {}, {} and {}). Repeat each parameter once per filter."
    )


class FilterKeys:
    FIELD: str = "field"
    OPERATOR: str = "operator"
    VALUE: str = "value"
    DIRECTION: str = "direction"


class CustomFilterFields:
    LAST_ACTIVITY_DATE: str = "last_activity_date"
    UPDATED_AT: str = "updated_at"


class FilterOperator:
    """
    Canonical filter operators plus the word aliases the story asks for
    (Equals, Before, After, Between), on top of the symbols the builder
    already supported (=, !=, <=, >=, LIKE, IN, BETWEEN).
    """

    EQUALS: str = "="
    NOT_EQUALS: str = "!="
    LESS_THAN: str = "<"
    GREATER_THAN: str = ">"
    LESS_THAN_OR_EQUAL: str = "<="
    GREATER_THAN_OR_EQUAL: str = ">="
    LIKE: str = "LIKE"
    IN: str = "IN"
    BETWEEN: str = "BETWEEN"

    #: Operators that take a two element range instead of a scalar value.
    RANGE_OPERATORS: set = {BETWEEN}

    #: Operators that take a collection of values.
    COLLECTION_OPERATORS: set = {IN, BETWEEN}

    #: Aliases accepted from clients, keyed by their upper cased form.
    ALIASES: dict = {
        "=": EQUALS,
        "EQUALS": EQUALS,
        "!=": NOT_EQUALS,
        "NOT_EQUALS": NOT_EQUALS,
        "<": LESS_THAN,
        "BEFORE": LESS_THAN,
        ">": GREATER_THAN,
        "AFTER": GREATER_THAN,
        "<=": LESS_THAN_OR_EQUAL,
        ">=": GREATER_THAN_OR_EQUAL,
        "LIKE": LIKE,
        "IN": IN,
        "BETWEEN": BETWEEN,
    }

    @classmethod
    def normalise(cls, operator) -> str:
        """
        Map a client supplied operator onto its canonical symbol.

        Unknown operators are returned untouched so the builder raises the
        existing "Unsupported operator" error with the value the client sent.
        """
        if not isinstance(operator, str):
            return operator
        return cls.ALIASES.get(operator.strip().upper(), operator.strip())

    @classmethod
    def supported(cls) -> list:
        """Every operator token a client may send, for validation and docs."""
        return sorted(cls.ALIASES.keys())


class DateFilterFormats:
    """Date formats accepted by date based filters, besides raw epoch millis."""

    #: A filter on one of these covers the whole day, e.g. "Created At =
    #: 01-Aug-2026" matches 00:00:00 - 23:59:59.999. %d-%b-%Y matches the
    #: story's own example date format; %Y-%m-%d is the common ISO form.
    DATE_ONLY: tuple = (
        "%Y-%m-%d",
        "%d-%b-%Y",
    )


class BooleanFilterValues:
    """String forms accepted for boolean columns such as user status."""

    TRUE: set = {"true", "active"}
    FALSE: set = {"false", "inactive"}
