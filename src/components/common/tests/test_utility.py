from src.components.common.constants import FieldType
from src.components.common.utility import SchemaValidator


class TestSchemaValidator:
    """Test cases for SchemaValidator class."""

    def test_validate_success_single_field(self):
        """Test successful validation of a single field."""
        fields = {
            "user_id": {"value": 123, "required": True, "type": FieldType.INTEGER}
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"user_id": 123}

    def test_validate_success_multiple_fields(self):
        """Test successful validation of multiple fields."""
        fields = {
            "user_id": {
                "value": 123,
                "required": True,
                "type": FieldType.INTEGER,
                "min": 1,
            },
            "name": {
                "value": "John Doe",
                "required": True,
                "type": FieldType.STRING,
                "min": 3,
                "max": 50,
            },
            "score": {"value": 95.5, "type": FieldType.FLOAT, "min": 0, "max": 100},
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"user_id": 123, "name": "John Doe", "score": 95.5}

    def test_validate_required_field_missing(self):
        """Test validation fails when required field is None."""
        fields = {"user_id": {"value": None, "required": True}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "user_id is required"

    def test_validate_required_field_empty_string(self):
        """Test validation fails when required field is empty string."""
        fields = {"name": {"value": "", "required": True}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "name is required"

    def test_validate_optional_field_none(self):
        """Test optional field with None value passes."""
        fields = {"description": {"value": None, "required": False}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"description": None}

    # ========================================================================
    # Integer type tests
    # ========================================================================

    def test_validate_integer_valid(self):
        """Test valid integer validation."""
        fields = {"count": {"value": 42, "type": FieldType.INTEGER}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"count": 42}

    def test_validate_integer_string_conversion(self):
        """Test integer conversion from string."""
        fields = {"count": {"value": "42", "type": FieldType.INTEGER}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"count": 42}

    def test_validate_integer_invalid_string(self):
        """Test integer validation fails with invalid string."""
        fields = {"count": {"value": "abc", "type": FieldType.INTEGER}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "count must be a valid integer"

    def test_validate_integer_boolean_rejected(self):
        """Test boolean is rejected when integer expected."""
        fields = {"count": {"value": True, "type": FieldType.INTEGER}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "count must be an integer"

    def test_validate_integer_no_conversion(self):
        """Test integer validation without auto-conversion."""
        fields = {"count": {"value": "42", "type": FieldType.INTEGER, "convert": False}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "count must be an integer"

    def test_validate_integer_min_value(self):
        """Test integer minimum value validation."""
        fields = {"count": {"value": 5, "type": FieldType.INTEGER, "min": 10}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "count must be at least 10"

    def test_validate_integer_max_value(self):
        """Test integer maximum value validation."""
        fields = {"count": {"value": 100, "type": FieldType.INTEGER, "max": 50}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "count cannot exceed 50"

    def test_validate_integer_range_valid(self):
        """Test integer within valid range."""
        fields = {
            "count": {"value": 25, "type": FieldType.INTEGER, "min": 10, "max": 50}
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"count": 25}

    # ========================================================================
    # String type tests
    # ========================================================================

    def test_validate_string_valid(self):
        """Test valid string validation."""
        fields = {"name": {"value": "John Doe", "type": FieldType.STRING}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"name": "John Doe"}

    def test_validate_string_auto_conversion(self):
        """Test string auto-conversion from other types."""
        fields = {"name": {"value": 123, "type": FieldType.STRING}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"name": "123"}

    def test_validate_string_no_conversion(self):
        """Test string validation without auto-conversion."""
        fields = {"name": {"value": 123, "type": FieldType.STRING, "convert": False}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "name must be a string"

    def test_validate_string_min_length(self):
        """Test string minimum length validation."""
        fields = {"name": {"value": "Jo", "type": FieldType.STRING, "min": 3}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "name must be at least 3 characters"

    def test_validate_string_max_length(self):
        """Test string maximum length validation."""
        fields = {
            "name": {"value": "John Doe Long Name", "type": FieldType.STRING, "max": 10}
        }

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "name cannot exceed 10 characters"

    def test_validate_string_length_valid(self):
        """Test string within valid length range."""
        fields = {
            "name": {"value": "John", "type": FieldType.STRING, "min": 3, "max": 10}
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"name": "John"}

    # ========================================================================
    # Float type tests
    # ========================================================================

    def test_validate_float_valid(self):
        """Test valid float validation."""
        fields = {"score": {"value": 95.5, "type": FieldType.FLOAT}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"score": 95.5}

    def test_validate_float_integer_input(self):
        """Test float validation with integer input."""
        fields = {"score": {"value": 95, "type": FieldType.FLOAT}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"score": 95.0}

    def test_validate_float_string_conversion(self):
        """Test float conversion from string."""
        fields = {"score": {"value": "95.5", "type": FieldType.FLOAT}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"score": 95.5}

    def test_validate_float_invalid_string(self):
        """Test float validation fails with invalid string."""
        fields = {"score": {"value": "abc", "type": FieldType.FLOAT}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "score must be a valid number"

    def test_validate_float_boolean_rejected(self):
        """Test boolean is rejected when float expected."""
        fields = {"score": {"value": True, "type": FieldType.FLOAT, "convert": False}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "score must be a number"

    def test_validate_float_min_value(self):
        """Test float minimum value validation."""
        fields = {"score": {"value": 50.0, "type": FieldType.FLOAT, "min": 60.0}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "score must be at least 60.0"

    def test_validate_float_max_value(self):
        """Test float maximum value validation."""
        fields = {"score": {"value": 110.0, "type": FieldType.FLOAT, "max": 100.0}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "score cannot exceed 100.0"

    def test_validate_float_range_valid(self):
        """Test float within valid range."""
        fields = {
            "score": {"value": 75.5, "type": FieldType.FLOAT, "min": 0.0, "max": 100.0}
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"score": 75.5}

    # ========================================================================
    # Boolean type tests
    # ========================================================================

    def test_validate_boolean_true(self):
        """Test boolean validation with True."""
        fields = {"is_active": {"value": True, "type": FieldType.BOOLEAN}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"is_active": True}

    def test_validate_boolean_false(self):
        """Test boolean validation with False."""
        fields = {"is_active": {"value": False, "type": FieldType.BOOLEAN}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"is_active": False}

    def test_validate_boolean_string_true_variants(self):
        """Test boolean conversion from string 'true' variants."""
        for value in ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]:
            fields = {"is_active": {"value": value, "type": FieldType.BOOLEAN}}

            validated, error = SchemaValidator.validate(fields)

            assert error is None, f"Failed for value: {value}"
            assert validated == {"is_active": True}, f"Failed for value: {value}"

    def test_validate_boolean_string_false_variants(self):
        """Test boolean conversion from string 'false' variants."""
        for value in ["false", "False", "FALSE", "0", "no", "No", "NO"]:
            fields = {"is_active": {"value": value, "type": FieldType.BOOLEAN}}

            validated, error = SchemaValidator.validate(fields)

            assert error is None, f"Failed for value: {value}"
            assert validated == {"is_active": False}, f"Failed for value: {value}"

    def test_validate_boolean_invalid_string(self):
        """Test boolean validation fails with invalid string."""
        fields = {"is_active": {"value": "maybe", "type": FieldType.BOOLEAN}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "is_active must be a boolean"

    def test_validate_boolean_no_conversion(self):
        """Test boolean validation without auto-conversion."""
        fields = {
            "is_active": {
                "value": "true",
                "type": FieldType.BOOLEAN,
                "convert": False,
            }
        }

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "is_active must be a boolean"

    def test_validate_boolean_integer_rejected(self):
        """Test integer is rejected when boolean expected without conversion."""
        fields = {
            "is_active": {"value": 1, "type": FieldType.BOOLEAN, "convert": False}
        }

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "is_active must be a boolean"

    # ========================================================================
    # Whitelist/values tests
    # ========================================================================

    def test_validate_values_whitelist_valid(self):
        """Test validation with allowed values - valid."""
        fields = {
            "status": {
                "value": "active",
                "values": ["active", "inactive", "pending"],
            }
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"status": "active"}

    def test_validate_values_whitelist_invalid(self):
        """Test validation with allowed values - invalid."""
        fields = {
            "status": {
                "value": "deleted",
                "values": ["active", "inactive", "pending"],
            }
        }

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "status must be one of: active, inactive, pending"

    def test_validate_values_integer_whitelist(self):
        """Test validation with integer whitelist."""
        fields = {
            "priority": {"value": 2, "type": FieldType.INTEGER, "values": [1, 2, 3]}
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"priority": 2}

    def test_validate_values_integer_whitelist_invalid(self):
        """Test validation with integer whitelist - invalid."""
        fields = {
            "priority": {"value": 5, "type": FieldType.INTEGER, "values": [1, 2, 3]}
        }

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "priority must be one of: 1, 2, 3"

    def test_validate_complex_scenario(self):
        """Test complex validation with multiple rules."""
        fields = {
            "service_board_id": {
                "value": "100",
                "required": True,
                "type": FieldType.INTEGER,
                "min": 1,
                "max": 2147483647,
            },
            "limit": {"value": 10, "type": FieldType.INTEGER, "min": 1, "max": 100},
            "offset": {"value": 0, "type": FieldType.INTEGER, "min": 0},
            "filter": {
                "value": "today",
                "values": ["today", "yesterday", "last_week", "last_month"],
            },
            "is_enabled": {"value": "true", "type": FieldType.BOOLEAN},
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {
            "service_board_id": 100,
            "limit": 10,
            "offset": 0,
            "filter": "today",
            "is_enabled": True,
        }

    def test_validate_multiple_errors_returns_first(self):
        """Test that validation returns the first error encountered."""
        fields = {
            "field1": {"value": None, "required": True},
            "field2": {"value": "abc", "type": FieldType.INTEGER},
        }

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        # Should return the first field's error
        assert error == "field1 is required"

    def test_validate_no_type_specified(self):
        """Test validation without type specification."""
        fields = {"name": {"value": "John Doe", "min": 3, "max": 50}}

        validated, error = SchemaValidator.validate(fields)

        # Should validate min/max as string length
        assert error is None
        assert validated == {"name": "John Doe"}

    def test_validate_only_min_specified(self):
        """Test validation with only min value."""
        fields = {"count": {"value": 50, "type": FieldType.INTEGER, "min": 10}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"count": 50}

    def test_validate_only_max_specified(self):
        """Test validation with only max value."""
        fields = {"count": {"value": 50, "type": FieldType.INTEGER, "max": 100}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"count": 50}

    def test_validate_empty_config(self):
        """Test validation with minimal config."""
        fields = {"name": {"value": "John"}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"name": "John"}

    def test_validate_string_range_without_type(self):
        """Test string length validation without explicit type."""
        fields = {"description": {"value": "Short", "min": 10}}

        validated, error = SchemaValidator.validate(fields)

        assert validated == {}
        assert error == "description must be at least 10 characters"

    def test_validate_numeric_with_string_type(self):
        """Test numeric value with string type and range."""
        fields = {
            "code": {"value": "12345", "type": FieldType.STRING, "min": 5, "max": 10}
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"code": "12345"}

    def test_validate_negative_integers(self):
        """Test validation with negative integers."""
        fields = {"temperature": {"value": -10, "type": FieldType.INTEGER, "min": -50}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"temperature": -10}

    def test_validate_zero_values(self):
        """Test validation with zero values."""
        fields = {
            "count": {"value": 0, "type": FieldType.INTEGER, "min": 0, "max": 100}
        }

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"count": 0}

    def test_validate_float_from_integer_string(self):
        """Test float conversion from integer string."""
        fields = {"score": {"value": "100", "type": FieldType.FLOAT}}

        validated, error = SchemaValidator.validate(fields)

        assert error is None
        assert validated == {"score": 100.0}

    def test_validate_empty_string_length(self):
        """Test empty string against min length (after required check)."""
        fields = {
            "name": {"value": "", "required": False, "type": FieldType.STRING, "min": 3}
        }

        validated, error = SchemaValidator.validate(fields)

        # Empty string bypasses required but not length check since value is checked first
        # Actually, the code checks if field_value is "" in the required check and returns None, None
        # So this should pass with None value
        assert error is None
        assert validated == {"name": None}
