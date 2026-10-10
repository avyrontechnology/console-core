from src.components.filters.constants import FilterCriteriaMessage


class BaseFilterCriteria:
    """
    BaseFilterCriteria is a class that manages a collection of filter conditions.

    Attributes:
        filters (list): A list of dictionaries where each dictionary represents a filter condition.

    Methods:
        __init__():
            Initializes the BaseFilterCriteria with an empty list of filters.

        add_filter(field, operator, value):
            Adds a filter condition to the filters list.

            Args:
                field (str): The field to which the filter condition applies.
                operator (str): The operator to use for the filter condition (e.g., '=', '>', '<').
                value (any): The value to compare the field against.
    """

    def __init__(self):
        self.filters = []  # List of filter conditions
        self.group_by = []  # List of fields to group by
        self.aggregations = []  # List of aggregation functions
        self.order_by = []  # Optional sorting of the results

    def add_filter(self, field, operator, value):
        """Adds a filter condition."""
        self.filters.append({"field": field, "operator": operator, "value": value})

    def add_group_by(self, field):
        """Add a field to group by."""
        self.group_by.append(field)

    def add_aggregation(self, field, agg_function):
        """Add an aggregation function (sum, avg, etc.) for a field."""
        self.aggregations.append({"field": field, "function": agg_function})

    def add_order_by(self, field, direction="ASC"):
        """Add sorting for the result."""
        self.order_by.append({"field": field, "direction": direction})

    @classmethod
    def from_query_params(cls, fields, operators, values) -> "BaseFilterCriteria":
        """
        Build criteria from the parallel query parameter lists used by listing GETs.

        The three lists line up positionally, so
        ?filter_by_fields=is_active&operators=EQUALS&values=true
        &filter_by_fields=role_id&operators=EQUALS&values=4
        reads as "is_active = true AND role_id = 4". Operators that take two
        values (BETWEEN) carry them in one comma separated entry.

        Raises:
            ValueError: if the three lists are not the same length.
        """
        fields = list(fields or [])
        operators = list(operators or [])
        values = list(values or [])

        if not len(fields) == len(operators) == len(values):
            raise ValueError(
                FilterCriteriaMessage.PARALLEL_LENGTH_MISMATCH.format(
                    len(fields), len(operators), len(values)
                )
            )

        criteria = cls()
        for field, operator, value in zip(fields, operators, values):
            criteria.add_filter(field, operator, value)
        return criteria
