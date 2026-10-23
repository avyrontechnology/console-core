import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID

from sqlalchemy.inspection import inspect

from src.components.common.constants import FieldType


class CommonUtility:
    """
    Define common used function here
    """

    @staticmethod
    def model_to_dict(model: Any) -> dict:
        """Convert SQLAlchemy model instance to a dictionary."""
        if model is None:
            return {}
        mapper = inspect(model.__class__)
        return {c.key: getattr(model, c.key) for c in mapper.column_attrs}

    @staticmethod
    def serialize_data(data: Any) -> Any:
        """Serialize data to a JSON-compatible format."""
        if isinstance(data, list):
            return [
                (
                    CommonUtility.model_to_dict(item)
                    if hasattr(item, "__table__")
                    else item
                )
                for item in data
            ]
        elif hasattr(data, "__table__"):
            return CommonUtility.model_to_dict(data)
        return data

    @staticmethod
    def object_to_dict(obj: Any) -> Any:
        try:
            """
            Recursively converts an object into dictionary.
            Handles datetime objects by converting them to ISO 8601 strings.
            """

            if hasattr(obj, "__dict__"):

                return {
                    key: CommonUtility.object_to_dict(value)
                    for key, value in obj.__dict__.items()
                    if not key.startswith("_")
                }
            elif isinstance(obj, list):
                return [CommonUtility.object_to_dict(item) for item in obj]
            elif isinstance(obj, datetime):
                return obj.isoformat()
            return obj
        except Exception as e:
            pass

    @staticmethod
    def camel_to_snake(name: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class SchemaValidator:
    """
    Single-method validation utility.
    All validations done through one method based on parameters.
    """

    @staticmethod
    def validate(
        fields: Dict[str, Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Universal validator - validates multiple fields based on their config.

        Args:
            fields: Dictionary where:
                - key: field name
                - value: dict with validation rules

        Validation rules (all optional except 'value'):
            - value: The value to validate (required)
            - required: bool - Field must be provided
            - type: FieldType - Expected type (INTEGER, STRING, FLOAT, BOOLEAN)
            - min: int/float - Minimum value (for numbers) or length (for strings)
            - max: int/float - Maximum value (for numbers) or length (for strings)
            - values: List - Allowed values (whitelist)
            - convert: bool - Auto-convert types (default: True)

        Returns:
            Tuple[validated_dict, error_message]
            - Success: ({field: value, ...}, None)
            - Failure: ({}, "error message")

        Example:
            result, error = Validator.validate({
                "service_board_id": {
                    "value": raw_id,
                    "required": True,
                    "type": FieldType.INTEGER,
                    "min": 1,
                    "max": 2147483647
                },
                "limit": {
                    "value": raw_limit,
                    "type": FieldType.INTEGER,
                    "min": 1
                },
                "offset": {
                    "value": raw_offset,
                    "type": FieldType.INTEGER,
                    "min": 1
                }
            })

            if error:
                return BadRequestResponse(detail=error)
        """
        validated: Dict[str, Any] = {}

        for field_name, config in fields.items():
            # Extract configuration
            field_value = config.get("value")
            is_required = config.get("required", False)
            field_type = config.get("type")
            min_val = config.get("min")
            max_val = config.get("max")
            allowed_values = config.get("values")
            auto_convert = config.get("convert", True)

            # Validate this field
            value, error = SchemaValidator._validate_field(
                field_name=field_name,
                field_value=field_value,
                is_required=is_required,
                field_type=field_type,
                min_val=min_val,
                max_val=max_val,
                allowed_values=allowed_values,
                auto_convert=auto_convert,
            )

            if error:
                return {}, error

            validated[field_name] = value

        return validated, None

    @staticmethod
    def _validate_field(
        field_name: str,
        field_value: Any,
        is_required: bool,
        field_type: Optional[FieldType],
        min_val: Optional[Union[int, float]],
        max_val: Optional[Union[int, float]],
        allowed_values: Optional[List[Any]],
        auto_convert: bool,
    ) -> Tuple[Any, Optional[str]]:
        """Internal method to validate a single field"""

        # Check required
        if field_value is None or field_value == "":
            if is_required:
                return None, f"{field_name} is required"
            return None, None

        # Type validation & conversion
        if field_type:
            field_value, error = SchemaValidator._check_type(
                field_name, field_value, field_type, auto_convert
            )
            if error:
                return None, error

        # Range/Length validation
        if min_val is not None or max_val is not None:
            error = SchemaValidator._check_range(
                field_name, field_value, field_type, min_val, max_val
            )
            if error:
                return None, error

        # Whitelist validation
        if allowed_values:
            error = SchemaValidator._check_whitelist(
                field_name, field_value, allowed_values
            )
            if error:
                return None, error

        return field_value, None

    @staticmethod
    def _check_type(
        field_name: str,
        value: Any,
        field_type: FieldType,
        auto_convert: bool,
    ) -> Tuple[Any, Optional[str]]:
        """Check and convert type"""

        # Dispatch to specific type checker
        type_checkers = {
            FieldType.INTEGER: SchemaValidator._check_integer_type,
            FieldType.STRING: SchemaValidator._check_string_type,
            FieldType.FLOAT: SchemaValidator._check_float_type,
            FieldType.BOOLEAN: SchemaValidator._check_boolean_type,
            FieldType.DICT: SchemaValidator._check_dict_type,
            FieldType.UUID: SchemaValidator._check_uuid_type,
        }

        checker = type_checkers.get(field_type)
        if checker:
            return checker(field_name, value, auto_convert)

        return value, None

    @staticmethod
    def _check_integer_type(
        field_name: str, value: Any, auto_convert: bool
    ) -> Tuple[Any, Optional[str]]:
        """Check and convert integer type"""
        # Auto-convert string to int
        if auto_convert and isinstance(value, str):
            try:
                return int(value), None
            except (ValueError, TypeError):
                return None, f"{field_name} must be a valid integer"

        # Check type (note: isinstance(True, int) is True, so exclude booleans)
        if not isinstance(value, int) or isinstance(value, bool):
            return None, f"{field_name} must be an integer"

        return value, None

    @staticmethod
    def _check_uuid_type(
        field_name: str, value: Any, auto_convert: bool
    ) -> Tuple[Any, Optional[str]]:
        """Check UUID type: accept UUID objects and canonical UUID strings.

        Plain ints/floats are rejected (no silent int->UUID coercion at the
        API boundary); strings are parsed strictly.
        """
        if isinstance(value, UUID):
            return value, None
        if isinstance(value, str):
            try:
                return UUID(value), None
            except (ValueError, AttributeError, TypeError):
                return None, f"{field_name} must be a valid UUID"
        return None, f"{field_name} must be a valid UUID"

    @staticmethod
    def _check_string_type(
        field_name: str, value: Any, auto_convert: bool
    ) -> Tuple[Any, Optional[str]]:
        """Check and convert string type"""
        if isinstance(value, str):
            return value, None

        if auto_convert:
            return str(value), None

        return None, f"{field_name} must be a string"

    @staticmethod
    def _check_float_type(
        field_name: str, value: Any, auto_convert: bool
    ) -> Tuple[Any, Optional[str]]:
        """Check and convert float type"""
        if auto_convert:
            try:
                return float(value), None
            except (ValueError, TypeError):
                return None, f"{field_name} must be a valid number"

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None, f"{field_name} must be a number"

        return float(value), None

    @staticmethod
    def _check_boolean_type(
        field_name: str, value: Any, auto_convert: bool
    ) -> Tuple[Any, Optional[str]]:
        """Check and convert boolean type"""
        if isinstance(value, bool):
            return value, None

        if auto_convert and isinstance(value, str):
            return SchemaValidator._convert_string_to_boolean(value, field_name)

        return None, f"{field_name} must be a boolean"

    @staticmethod
    def _check_dict_type(
        field_name: str, value: Any, auto_convert: bool
    ) -> Tuple[Any, Optional[str]]:
        """Check and convert dict type"""
        if isinstance(value, dict):
            return value, None

        if auto_convert and isinstance(value, str):
            try:
                parsed = json.loads(value)
                if not isinstance(parsed, dict):
                    return None, f"{field_name} must be a valid object"
                return parsed, None
            except (ValueError, TypeError):
                return None, f"{field_name} must be a valid JSON object"

        return None, f"{field_name} must be an object"

    @staticmethod
    def _convert_string_to_boolean(
        value: str, field_name: str
    ) -> Tuple[Any, Optional[str]]:
        """Convert string value to boolean"""
        lower_val = value.lower()

        if lower_val in ["true", "1", "yes"]:
            return True, None

        if lower_val in ["false", "0", "no"]:
            return False, None

        return None, f"{field_name} must be a boolean"

    @staticmethod
    def _check_range(
        field_name: str,
        value: Any,
        field_type: Optional[FieldType],
        min_val: Optional[Union[int, float]],
        max_val: Optional[Union[int, float]],
    ) -> Optional[str]:
        """Check numeric range or string length"""

        # For numbers: check value range
        if field_type in [FieldType.INTEGER, FieldType.FLOAT]:
            if min_val is not None and value < min_val:
                return f"{field_name} must be at least {min_val}"

            if max_val is not None and value > max_val:
                return f"{field_name} cannot exceed {max_val}"

        # For strings: check length
        elif field_type == FieldType.STRING or isinstance(value, str):
            length = len(value)

            if min_val is not None and length < min_val:
                return f"{field_name} must be at least {min_val} characters"

            if max_val is not None and length > max_val:
                return f"{field_name} cannot exceed {max_val} characters"

        return None

    @staticmethod
    def _check_whitelist(
        field_name: str, value: Any, allowed_values: List[Any]
    ) -> Optional[str]:
        """Check if value is in allowed list"""

        if value not in allowed_values:
            allowed_str = ", ".join(str(v) for v in allowed_values)
            return f"{field_name} must be one of: {allowed_str}"

        return None
