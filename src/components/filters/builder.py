from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import Integer, String, func, select, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Query
from sqlalchemy.sql.elements import ClauseElement
from sqlalchemy.sql.expression import and_, exists, literal, not_, or_

from src.components.filters.constants import (
    BooleanFilterValues,
    BuilderExceptionMessage,
    CustomFilterFields,
    DateFilterFormats,
    FilterKeys,
    FilterOperator,
)
from src.components.filters.criteria import BaseFilterCriteria
from src.exceptions import UserException



class BaseFilterBuilder:
    """
    A builder class for constructing SQLAlchemy queries based on filter criteria.

    Attributes:
        models (list): The SQLAlchemy models involved in the query.
        criteria (BaseFilterCriteria): The filter criteria to apply to the query.
        base_query (Query): The initial query before applying filters.
        date_fields (set): Filter field names stored as epoch millisecond
            columns. A subclass declares its own set to opt those fields into
            date aware comparisons (whole day Equals, Before, After, Between).

    Methods:
        build_query() -> Query:
            Constructs and returns a SQLAlchemy query based on the provided filter criteria.
    """

    #: Overridden by subclasses that expose timestamp columns as filters.
    date_fields: set = set()

    def __init__(self, models: list, criteria: BaseFilterCriteria, base_query: Query):

        self.models = models
        self.criteria = criteria
        self.base_query = base_query

    async def build_query(self) -> Query: # NOSONAR
        """
        Build the SQLAlchemy query dynamically based on provided criteria.

        """
        query = self.base_query

        # Apply filters
        filter_conditions = []
        for filter_item in self.criteria.filters:
            field_name = filter_item.get(FilterKeys.FIELD)
            operator = FilterOperator.normalise(filter_item.get(FilterKeys.OPERATOR))
            value = filter_item.get(FilterKeys.VALUE)

            # Hook for custom logic from child class
            handled = self.handle_custom_filter(query, field_name, value)
            if handled is not None:
                query = handled
                continue

            field = self._resolve_field_from_models(field_name)

            # Timestamp columns compare against day boundaries rather than a
            # single millisecond, so they bypass the generic casting path.
            if field_name in self.date_fields:
                filter_conditions.append(
                    self._build_date_condition(field, field_name, operator, value)
                )
                continue

            column_type = field.property.columns[0].type

            # Casts the filter value based on SQLAlchemy column type and operator.
            value = self._cast_filter_value(value, operator, column_type)

            # Mapping Operators
            condition = self._build_operator_condition(
                operator, field, value, column_type
            )

            filter_conditions.append(condition)

        if filter_conditions:
            query = query.where(and_(*filter_conditions))

        query = self._apply_group_by_fields(query)

        # Apply aggregations
        query = self._apply_aggregations(query)

        # Apply Ordering
        query = self._apply_ordering(query)

        return query

    def handle_custom_filter(self, query, field_name, value): # NOSONAR
        """Override this in child to handle special filters."""
        return None

    def _resolve_field_from_models(self, field_name: str):
        """
        Returns the ORM field (Column) for a given field name from available models.
        Raises an AttributeError if not found.
        """
        for model in self.models:
            if hasattr(model, field_name):
                return getattr(model, field_name)

        raise AttributeError(
            BuilderExceptionMessage.FIELD_NOT_EXIST.format(
                field_name, [m.__name__ for m in self.models]
            )
        )

    def _as_value_list(self, value) -> list:
        """
        Normalises a multi valued filter payload into a list.

        Clients send either a JSON array (["a", "b"]) or the legacy comma
        separated string ("a,b"); both are accepted.
        """
        if isinstance(value, (list, tuple)):
            return [item.strip() if isinstance(item, str) else item for item in value]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",")]
        return [value]

    def _coerce_boolean(self, value) -> bool:
        """
        Accepts the boolean forms the Status filter sends.

        A real JSON boolean is passed through; the string forms "true"/"false"
        and "active"/"inactive" are mapped onto one. Anything else is
        rejected so a typo cannot silently become False.
        """
        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            if value in (0, 1):
                return bool(value)
        elif isinstance(value, str):
            normalised = value.strip().lower()
            if normalised in BooleanFilterValues.TRUE:
                return True
            if normalised in BooleanFilterValues.FALSE:
                return False

        raise ValueError(
            BuilderExceptionMessage.INVALID_BOOLEAN_VALUE.format(
                value, type(value).__name__
            )
        )

    def _cast_filter_value(self, value: str, operator: str, column_type):
        """
        Casts the filter value based on SQLAlchemy column type and operator.
        """
        try:
            if operator in FilterOperator.COLLECTION_OPERATORS:
                value = self._as_value_list(value)
                if isinstance(column_type, Boolean):
                    return [self._coerce_boolean(item) for item in value]
                elif isinstance(column_type, Integer):
                    return [int(item) for item in value]
                elif isinstance(column_type, PG_UUID):
                    return [UUID(str(item)) for item in value]
                elif isinstance(column_type, String):
                    return [
                        item.lower() if isinstance(item, str) else item
                        for item in value
                    ]
                return value

            if isinstance(column_type, Boolean):
                return self._coerce_boolean(value)

            if isinstance(column_type, Integer):
                return int(value)
            elif isinstance(column_type, PG_UUID):
                return UUID(str(value))
            elif isinstance(column_type, String):
                return value.lower()

            return value
        except (ValueError, SyntaxError, TypeError) as exec:
            raise UserException(
                str(exec)
            )

    def _to_epoch_millis(self, moment: datetime) -> int:
        """Converts a datetime into the epoch millisecond form used by columns."""
        return int(moment.timestamp() * 1000)

    def _parse_date_bounds(self, value, field_name: str) -> tuple:
        """
        Resolves a single date filter value into its (lower, upper) millisecond bounds.

        A date-only value covers the whole day, so "01-Aug-2026" yields
        00:00:00.000 - 23:59:59.999. Epoch milliseconds resolve to a single
        instant instead, where both bounds are equal.
        """
        if isinstance(value, bool) or value is None:
            raise UserException(
                BuilderExceptionMessage.INVALID_DATE_VALUE.format(value, field_name)
            )

        # Epoch milliseconds, as a number or a numeric string.
        if isinstance(value, (int, float)):
            return int(value), int(value)

        if isinstance(value, str):
            candidate = value.strip()

            if candidate.lstrip("-").isdigit():
                return int(candidate), int(candidate)

            for date_format in DateFilterFormats.DATE_ONLY:
                try:
                    day = datetime.strptime(candidate, date_format)
                except ValueError:
                    continue
                start_of_day = self._to_epoch_millis(day)
                end_of_day = (
                    self._to_epoch_millis(day + timedelta(days=1)) - 1
                )
                return start_of_day, end_of_day

        raise UserException(
            BuilderExceptionMessage.INVALID_DATE_VALUE.format(value, field_name)
        )

    def _build_date_condition(self, field, field_name: str, operator: str, value):
        """
        Builds a condition for an epoch millisecond column.

        Comparisons are made against day boundaries so that a date only filter
        behaves the way a user reading the column expects: "Created At equals
        01-Aug-2026" matches everything recorded on that day, and "after
        01-Aug-2026" starts from the following midnight.
        """
        if operator == FilterOperator.BETWEEN:
            values = self._as_value_list(value)
            if len(values) != 2:
                raise UserException(
                    BuilderExceptionMessage.INVALID_RANGE_VALUE.format(
                        operator, field_name, len(values)
                    )
                )
            range_start, _ = self._parse_date_bounds(values[0], field_name)
            _, range_end = self._parse_date_bounds(values[1], field_name)
            return and_(field >= range_start, field <= range_end)

        lower, upper = self._parse_date_bounds(value, field_name)

        date_operator_map = {
            FilterOperator.EQUALS: lambda: and_(field >= lower, field <= upper),
            FilterOperator.NOT_EQUALS: lambda: or_(field < lower, field > upper),
            FilterOperator.LESS_THAN: lambda: field < lower,
            FilterOperator.LESS_THAN_OR_EQUAL: lambda: field <= upper,
            FilterOperator.GREATER_THAN: lambda: field > upper,
            FilterOperator.GREATER_THAN_OR_EQUAL: lambda: field >= lower,
        }

        if operator not in date_operator_map:
            raise UserException(
                BuilderExceptionMessage.UNSUPPORTED_DATE_OPERATOR.format(
                    operator, field_name
                )
            )

        return date_operator_map[operator]()

    def _build_operator_condition(self, operator: str, field, value, column_type):
        """
        Maps the given operator to a SQLAlchemy condition expression.
        """
        operator_map = {
            "=": lambda field_obj, val, col_type: (
                func.lower(field_obj) == val
                if isinstance(col_type, String)
                else field_obj == val
            ),
            "<": lambda field_obj, val, col_type: field_obj < val,
            ">": lambda field_obj, val, col_type: field_obj > val,
            "<=": lambda field_obj, val, col_type: field_obj <= val,
            ">=": lambda field_obj, val, col_type: field_obj >= val,
            "!=": lambda field_obj, val, col_type: (
                func.lower(field_obj) != val
                if isinstance(col_type, String)
                else field_obj != val
            ),
            "LIKE": lambda field_obj, val, col_type: (
                func.lower(field_obj).like(f"%{val}%")
                if isinstance(col_type, String)
                else None
            ),
            "BETWEEN": lambda field_obj, val, col_type: and_(
                field_obj >= val[0], field_obj <= val[1]
            ),
            "IN": lambda field_obj, val, col_type: (
                func.lower(field_obj).in_(val)
                if isinstance(col_type, String)
                else field_obj.in_(val)
            ),
        }

        if operator not in operator_map:
            raise ValueError(
                BuilderExceptionMessage.UNSUPPORTED_OPERATOR.format(operator)
            )

        condition = operator_map[operator](field, value, column_type)

        if condition is None:
            raise ValueError(
                BuilderExceptionMessage.UNSUPPORTED_OPERATOR_FOR_INT.format(operator)
            )

        return condition

    def _apply_group_by_fields(self, query):
        """
        Applies GROUP BY clauses to the query based on criteria.group_by.
        """
        if not self.criteria.group_by:
            return query

        group_by_fields = []
        for field_name in self.criteria.group_by:
            for model in self.models:
                if hasattr(model, field_name):
                    group_by_fields.append(getattr(model, field_name))
                    break

        if group_by_fields:
            query = query.group_by(*group_by_fields)

        return query

    def _apply_aggregations(self, query):
        """
        Applies aggregation functions to the query based on criteria.aggregations.
        """
        for aggregation in self.criteria.aggregations:
            aggregation_function = getattr(func, aggregation["function"])
            field_name = aggregation["field"]

            field = None
            for model in self.models:
                if hasattr(model, field_name):
                    field = getattr(model, field_name)
                    break

            if not field:
                raise AttributeError(
                    BuilderExceptionMessage.FIELD_NOT_EXIST.format(
                        field_name, [model.__name__ for model in self.models]
                    )
                )

            query = query.add_columns(aggregation_function(field).label(field_name))

        return query

    def _apply_ordering(self, query):
        """
        Applies ORDER BY clauses and DISTINCT to the query based on criteria.order_by.
        """
        order_fields = []

        for order in self.criteria.order_by:
            field_name = order["field"]
            direction = order.get("direction", "ASC")

            field = self._resolve_field_from_models(field_name)

            order_expr = (
                field.asc().nulls_last()
                if direction == "ASC"
                else field.desc().nulls_last()
            )

            order_fields.append(order_expr)

        return query.order_by(*order_fields)
