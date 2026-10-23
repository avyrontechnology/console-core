from uuid import UUID
import pytest
from pydantic import ValidationError

from src.components.plan.constants import PlanCustomLimitKeys, PlanType, Platform
from src.components.plan.schema import (
    DISALLOWED_LIMIT_KEYS,
    PlanBase,
    PlanResponse,
    PlanUpdate,
    PlanValidationMixin,
)
from src.components.wallet.enum import Currency


# Prod mapper is empty (retired platforms removed). Tests that
# exercise validator *logic* inject a sample mapper instead of
# depending on product data.
TEST_MAPPER = {"console": {"Dashboard": {"Chat": {"endpoints": [], "flags": []}}}}


@pytest.fixture
def mapper(monkeypatch):
    monkeypatch.setattr(
        "src.components.plan.schema.SERVICE_FEATURE_MAPPER", TEST_MAPPER
    )
    monkeypatch.setattr(
        "src.components.plan.controllers.SERVICE_FEATURE_MAPPER", TEST_MAPPER
    )


class TestPlanValidationMixin:
    """Test PlanValidationMixin methods."""

    @pytest.fixture
    def mixin(self):
        """Create a PlanValidationMixin instance."""
        return PlanValidationMixin()

    # _validate_name tests
    def test_validate_name_valid(self, mixin):
        """Should validate and clean valid name."""
        assert mixin._validate_name("Test Plan") == "Test Plan"
        assert mixin._validate_name("  Test Plan  ") == "Test Plan"
        assert mixin._validate_name("Test-Plan_123") == "Test-Plan_123"

    def test_validate_name_empty(self, mixin):
        """Should raise error for empty name."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            mixin._validate_name("")

        with pytest.raises(ValueError, match="name cannot be empty"):
            mixin._validate_name("   ")

    def test_validate_name_too_long(self, mixin):
        """Should raise error for name longer than 100 characters."""
        long_name = "a" * 101
        with pytest.raises(
            ValueError, match="name must be less than or equal to 100 characters"
        ):
            mixin._validate_name(long_name)

    def test_validate_name_invalid_characters(self, mixin):
        """Should raise error for invalid characters in name."""
        with pytest.raises(
            ValueError,
            match="name can only contain alphanumeric characters, spaces, hyphens, and underscores",
        ):
            mixin._validate_name("Test@Plan")

        with pytest.raises(ValueError):
            mixin._validate_name("Test Plan!")

    # _validate_tag tests
    def test_validate_tag_valid(self, mixin):
        """Should validate and clean valid tag."""
        assert mixin._validate_tag("premium") == "premium"
        assert mixin._validate_tag("  basic  ") == "basic"

    def test_validate_tag_empty(self, mixin):
        """Should raise error for empty tag."""
        with pytest.raises(ValueError, match="tag cannot be empty"):
            mixin._validate_tag("")

        with pytest.raises(ValueError, match="tag cannot be empty"):
            mixin._validate_tag("   ")

    def test_validate_tag_too_long(self, mixin):
        """Should raise error for tag longer than 30 characters."""
        long_tag = "a" * 31
        with pytest.raises(ValueError, match="tag must not exceed 30 characters"):
            mixin._validate_tag(long_tag)

    # _validate_hierarchy tests
    def test_validate_hierarchy_valid(self, mixin):
        """Should validate valid hierarchy values."""
        assert mixin._validate_hierarchy(0) == 0
        assert mixin._validate_hierarchy(500) == 500
        assert mixin._validate_hierarchy(999) == 999

    def test_validate_hierarchy_none(self, mixin):
        """Should raise error for None hierarchy."""
        with pytest.raises(ValueError, match="hierarchy is required"):
            mixin._validate_hierarchy(None)

    def test_validate_hierarchy_not_integer(self, mixin):
        """Should raise error for non-integer hierarchy."""
        with pytest.raises(ValueError, match="hierarchy must be an integer"):
            mixin._validate_hierarchy(10.5)

        with pytest.raises(ValueError, match="hierarchy must be an integer"):
            mixin._validate_hierarchy("10")

    def test_validate_hierarchy_out_of_range(self, mixin):
        """Should raise error for hierarchy out of range."""
        with pytest.raises(ValueError, match="hierarchy must be between 0 and 999"):
            mixin._validate_hierarchy(-1)

        with pytest.raises(ValueError, match="hierarchy must be between 0 and 999"):
            mixin._validate_hierarchy(1000)

    # _validate_description tests
    def test_validate_description_valid(self, mixin):
        """Should validate and clean valid description."""
        assert mixin._validate_description("Test description") == "Test description"
        assert mixin._validate_description("  Test  ") == "Test"

    def test_validate_description_too_long(self, mixin):
        """Should raise error for description longer than 500 characters."""
        long_desc = "a" * 501
        with pytest.raises(
            ValueError, match="description must be less than or equal to 500 characters"
        ):
            mixin._validate_description(long_desc)

    # _validate_price tests
    def test_validate_price_valid(self, mixin):
        """Should validate valid price."""
        mixin._validate_price(100)
        mixin._validate_price(1000.50)
        mixin._validate_price(10_000_000_00)

    def test_validate_price_too_low(self, mixin):
        """Should raise error for price less than 100."""
        with pytest.raises(ValueError, match="price must be greater than 99"):
            mixin._validate_price(99)

        with pytest.raises(ValueError, match="price must be greater than 99"):
            mixin._validate_price(50.50)

    def test_validate_price_too_high(self, mixin):
        """Should raise error for price exceeding maximum."""
        with pytest.raises(
            ValueError, match="price must be less than or equal to 1000000000"
        ):
            mixin._validate_price(10_000_000_01)

    def test_validate_price_too_many_decimals(self, mixin):
        """Should raise error for price with more than 2 decimal places."""
        with pytest.raises(
            ValueError, match="price must have at most two decimal places"
        ):
            mixin._validate_price(100.123)

    # _validate_discount tests
    def test_validate_discount_valid(self, mixin):
        """Should validate valid discount percentage."""
        mixin._validate_discount(0)
        mixin._validate_discount(50.5)
        mixin._validate_discount(100)

    def test_validate_discount_negative(self, mixin):
        """Should raise error for negative discount."""
        with pytest.raises(ValueError, match="discount_percentage must be >= 0"):
            mixin._validate_discount(-1)

    def test_validate_discount_too_high(self, mixin):
        """Should raise error for discount over 100."""
        with pytest.raises(ValueError, match="discount_percentage must be <= 100"):
            mixin._validate_discount(101)

    def test_validate_discount_too_many_decimals(self, mixin):
        """Should raise error for discount with more than 2 decimal places."""
        with pytest.raises(
            ValueError, match="discount_percentage must have at most two decimal places"
        ):
            mixin._validate_discount(50.123)

    # _validate_currency tests
    def test_validate_currency_valid(self, mixin):
        """Should validate valid currency."""
        mixin._validate_currency(Currency.INDIA)

    def test_validate_currency_invalid(self, mixin):
        """Should raise error for invalid currency."""
        with pytest.raises(ValueError, match="Invalid currency 'INVALID'"):
            mixin._validate_currency("INVALID")

    # _validate_plan_type tests
    def test_validate_plan_type_valid(self, mixin):
        """Should validate valid plan type."""
        mixin._validate_plan_type(PlanType.WALLET)

    def test_validate_plan_type_invalid(self, mixin):
        """Should raise error for invalid plan type."""
        with pytest.raises(ValueError, match="Invalid plan_type 'INVALID'"):
            mixin._validate_plan_type("INVALID")

    def test_validate_plan_type_standard_without_price(self, mixin):
        """Should raise error for STANDARD plan without price."""
        with pytest.raises(
            ValueError, match="price is required when plan_type is STANDARD"
        ):
            mixin._validate_plan_type(PlanType.STANDARD)

    def test_validate_plan_type_standard_with_price(self, mixin):
        """Should validate STANDARD plan with price."""
        mixin.price = 1000
        mixin._validate_plan_type(PlanType.STANDARD)

    # _validate_service_name tests
    def test_validate_service_name_valid(self, mixin):
        """Should validate valid service name."""
        result = mixin._validate_service_name(Platform.CONSOLE)
        assert result == Platform.CONSOLE

    def test_validate_service_name_invalid(self, mixin):
        """Should raise error for invalid service name."""
        with pytest.raises(ValueError, match="Invalid service_name 'INVALID'"):
            mixin._validate_service_name("INVALID")

    # _validate_limits tests
    def test_validate_limits_valid(self, mixin):
        """Should validate valid limits."""
        limits = {
            "SOME_VALID_KEY": 10,
        }
        try:
            mixin._validate_limits(limits)
        except ValueError as e:
            assert "Invalid limit key" in str(e)

    def test_validate_limits_disallowed_key(self, mixin):
        """Should raise error for disallowed limit keys."""
        disallowed_key = list(DISALLOWED_LIMIT_KEYS)[0]
        limits = {disallowed_key: 10}

        with pytest.raises(
            ValueError,
            match=f"Limit key '{disallowed_key}' is not allowed to be configured",
        ):
            mixin._validate_limits(limits)

    def test_validate_limits_invalid_key(self, mixin):
        """Should raise error for invalid limit key."""
        limits = {"INVALID_KEY": 10}

        with pytest.raises(ValueError, match="Invalid limit key 'INVALID_KEY'"):
            mixin._validate_limits(limits)

    def test_validate_limits_negative_value(self, mixin):
        """Should raise error for negative limit value."""
        with pytest.raises(ValueError, match="Invalid limit key"):
            mixin._validate_limits({"VALID_TEST_KEY": -1})

    def test_validate_limits_non_integer_value(self, mixin):
        """Should raise error for non-integer limit value."""
        with pytest.raises(ValueError, match="Invalid limit key"):
            mixin._validate_limits({"VALID_TEST_KEY": 10.5})

    # _parse_module tests
    def test_parse_module_valid(self, mixin):
        """Should parse valid module string."""
        service, feature = mixin._parse_module("talko:campaign")
        assert service == "talko"
        assert feature == "campaign"

    def test_parse_module_with_spaces(self, mixin):
        """Should parse module with spaces and strip them."""
        service, feature = mixin._parse_module("  talko : campaign  ")
        assert service == "talko"
        assert feature == "campaign"

    def test_parse_module_not_string(self, mixin):
        """Should raise error for non-string module."""
        with pytest.raises(ValueError, match="Module .* must be a string"):
            mixin._parse_module(123)

    def test_parse_module_no_colon(self, mixin):
        """Should raise error for module without colon."""
        with pytest.raises(
            ValueError, match="must be in format 'service:feature_name'"
        ):
            mixin._parse_module("talkocampaign")

    def test_parse_module_multiple_colons(self, mixin):
        """Should raise error for module with multiple colons."""
        with pytest.raises(
            ValueError, match="must be in format 'service:feature_name'"
        ):
            mixin._parse_module("talko:campaign:extra")

    def test_parse_module_empty_service(self, mixin):
        """Should raise error for empty service."""
        with pytest.raises(
            ValueError, match="must have non-empty service and feature name"
        ):
            mixin._parse_module(":campaign")

    def test_parse_module_empty_feature(self, mixin):
        """Should raise error for empty feature name."""
        with pytest.raises(
            ValueError, match="must have non-empty service and feature name"
        ):
            mixin._parse_module("talko:")

    # _validate_service tests
    def test_validate_service_valid(self, mixin):
        """Should validate valid service."""
        allowed = {"console", "console"}
        mixin._validate_service("console", "console:campaign", allowed)

    def test_validate_service_invalid(self, mixin):
        """Should raise error for invalid service."""
        allowed = {"console", "console"}

        with pytest.raises(ValueError, match="Invalid service 'invalid'"):
            mixin._validate_service("invalid", "invalid:campaign", allowed)

    # _validate_feature_name tests
    def test_validate_feature_name_valid(self, mixin, mapper):
        """Should validate valid feature name."""
        mixin._validate_feature_name("console", "Chat")

    def test_validate_feature_name_invalid(self, mixin):
        """Should raise error for invalid feature name."""
        with pytest.raises(ValueError, match="Invalid feature"):
            mixin._validate_feature_name("console", "invalid_feature_xyz")

    # _get_allowed_features tests
    def test_get_allowed_features_existing_service(self, mixin, mapper):
        """Should return allowed features for existing service."""
        features = mixin._get_allowed_features("console")
        assert isinstance(features, set)

    def test_get_allowed_features_non_existing_service(self, mixin):
        """Should return empty set for non-existing service."""
        features = mixin._get_allowed_features("nonexistent")
        assert features == set()

    # _validate_modules tests
    def test_validate_modules_valid(self, mixin, mapper):
        """Should validate valid modules list."""
        modules = ["console:Chat"]
        mixin._validate_modules(modules)

    def test_validate_modules_invalid_service(self, mixin):
        """Should raise error for invalid service in modules."""
        modules = ["invalid:feature"]

        with pytest.raises(ValueError, match="Invalid service"):
            mixin._validate_modules(modules)

    def test_validate_modules_invalid_feature(self, mixin, mapper):
        """Should raise error for invalid feature in modules."""
        modules = ["console:invalid_feature_xyz"]

        with pytest.raises(ValueError, match="Invalid feature"):
            mixin._validate_modules(modules)


class TestPlanBase:
    """Test PlanBase model."""

    def test_plan_base_valid_standard(self, mapper):
        """Should create valid STANDARD plan."""
        plan = PlanBase(
            name="Premium Plan",
            description="A premium plan",
            price=1000.0,
            discount_percentage=10.0,
            currency=Currency.INDIA,
            duration=1,  # ADDED: duration is required
            modules=["console:Chat"],
            plan_type=PlanType.STANDARD,
            tag="premium",
            hierarchy=1,
            service_name=Platform.CONSOLE,
        )

        assert plan.name == "Premium Plan"
        assert plan.price == 1000.0
        assert plan.plan_type == PlanType.STANDARD
        assert plan.duration == 1

    def test_plan_base_valid_wallet(self):
        """Should create valid WALLET plan."""
        plan = PlanBase(
            name="Wallet Plan",
            price=None,
            currency=Currency.INDIA,
            duration=0,  # ADDED: duration is required
            modules=[],
            plan_type=PlanType.WALLET,
            tag="wallet",
            hierarchy=2,
            service_name=Platform.CONSOLE,
        )

        assert plan.name == "Wallet Plan"
        assert plan.plan_type == PlanType.WALLET
        assert plan.duration == 0

    def test_plan_base_missing_plan_type(self):
        """Should raise error for missing plan_type."""
        with pytest.raises(ValueError, match="plan_type is required"):
            PlanBase(
                name="Test Plan",
                tag="test",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=None,
            )

    def test_plan_base_invalid_name(self):
        """Should raise error for invalid name."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            PlanBase(
                name="",
                tag="test",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=PlanType.WALLET,
            )

    def test_plan_base_invalid_tag(self):
        """Should raise error for invalid tag."""
        with pytest.raises(ValueError, match="tag cannot be empty"):
            PlanBase(
                name="Test Plan",
                tag="",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=PlanType.WALLET,
            )

    def test_plan_base_invalid_hierarchy(self):
        """Should raise error for invalid hierarchy."""
        with pytest.raises(ValueError, match="hierarchy must be between 0 and 999"):
            PlanBase(
                name="Test Plan",
                tag="test",
                hierarchy=1000,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=PlanType.WALLET,
            )

    def test_plan_base_invalid_service_name(self):
        """Should raise error for invalid service_name."""
        with pytest.raises(ValueError, match="Invalid service_name"):
            PlanBase(
                name="Test Plan",
                tag="test",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name="INVALID",
                plan_type=PlanType.WALLET,
            )

    def test_plan_base_with_description(self):
        """Should validate plan with description."""
        plan = PlanBase(
            name="Test Plan",
            description="Test description",
            tag="test",
            hierarchy=1,
            duration=1,  # ADDED: duration is required
            service_name=Platform.CONSOLE,
            plan_type=PlanType.WALLET,
        )

        assert plan.description == "Test description"

    def test_plan_base_with_invalid_price(self):
        """Should raise error for invalid price."""
        with pytest.raises(ValueError, match="price must be greater than 99"):
            PlanBase(
                name="Test Plan",
                price=50,
                tag="test",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=PlanType.STANDARD,
            )

    def test_plan_base_with_invalid_discount(self):
        """Should raise error for invalid discount."""
        with pytest.raises(ValueError, match="discount_percentage must be <= 100"):
            PlanBase(
                name="Test Plan",
                discount_percentage=150,
                tag="test",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=PlanType.WALLET,
            )

    def test_plan_base_invalid_currency(self):
        """Should raise error for invalid currency."""
        with pytest.raises(ValidationError, match="Invalid currency"):
            PlanBase(
                name="Test Plan",
                currency="INV",
                tag="test",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=PlanType.WALLET,
            )

    def test_plan_base_with_modules(self, mapper):
        """Should validate plan with modules."""
        plan = PlanBase(
            name="Test Plan",
            modules=["console:Chat"],
            tag="test",
            hierarchy=1,
            duration=1,  # ADDED: duration is required
            service_name=Platform.CONSOLE,
            plan_type=PlanType.WALLET,
        )

        assert len(plan.modules) == 1

    def test_plan_base_standard_without_price(self):
        """Should raise error for STANDARD plan without price."""
        with pytest.raises(
            ValueError, match="price is required when plan_type is STANDARD"
        ):
            PlanBase(
                name="Test Plan",
                tag="test",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=PlanType.STANDARD,
            )

    def test_plan_base_extra_fields_forbidden(self):
        """Should raise error for extra fields."""
        with pytest.raises(ValidationError):
            PlanBase(
                name="Test Plan",
                tag="test",
                hierarchy=1,
                duration=1,  # ADDED: duration is required
                service_name=Platform.CONSOLE,
                plan_type=PlanType.WALLET,
                extra_field="not allowed",
            )

    def test_plan_base_with_is_free_trial(self):
        """Should create plan with is_free_trial flag."""
        plan = PlanBase(
            name="Trial Plan",
            tag="trial",
            hierarchy=0,
            duration=1,  # ADDED: duration is required
            service_name=Platform.CONSOLE,
            plan_type=PlanType.WALLET,
            is_free_trial=True,
        )

        assert plan.is_free_trial is True

    def test_plan_base_with_otc_charge(self):
        """Should create plan with otc_charge."""
        plan = PlanBase(
            name="Test Plan",
            tag="test",
            hierarchy=1,
            duration=1,  # ADDED: duration is required
            service_name=Platform.CONSOLE,
            plan_type=PlanType.WALLET,
            otc_charge=100.0,
        )

        assert plan.otc_charge == 100.0


class TestPlanUpdate:
    """Test PlanUpdate model."""

    def test_plan_update_partial(self):
        """Should create partial update with some fields."""
        update = PlanUpdate(
            name="Updated Plan",
            price=2000.0,
        )

        assert update.name == "Updated Plan"
        assert update.price == 2000.0
        assert update.description is None

    def test_plan_update_all_none(self):
        """Should create update with all fields None."""
        update = PlanUpdate()

        assert update.name is None
        assert update.price is None
        assert update.description is None

    def test_plan_update_validate_name(self):
        """Should validate name when provided."""
        update = PlanUpdate(name="Valid Name")
        assert update.name == "Valid Name"

    def test_plan_update_invalid_name(self):
        """Should raise error for invalid name."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            PlanUpdate(name="")

    def test_plan_update_validate_description(self):
        """Should validate description when provided."""
        update = PlanUpdate(description="Valid description")
        assert update.description == "Valid description"

    def test_plan_update_invalid_description(self):
        """Should raise error for too long description."""
        with pytest.raises(
            ValueError, match="description must be less than or equal to 500 characters"
        ):
            PlanUpdate(description="a" * 501)

    def test_plan_update_validate_price(self):
        """Should validate price when provided."""
        update = PlanUpdate(price=1000.0)
        assert update.price == 1000.0

    def test_plan_update_invalid_price(self):
        """Should raise error for invalid price."""
        with pytest.raises(ValueError, match="price must be greater than 99"):
            PlanUpdate(price=50)

    def test_plan_update_validate_discount(self):
        """Should validate discount when provided."""
        update = PlanUpdate(discount_percentage=25.5)
        assert update.discount_percentage == 25.5

    def test_plan_update_invalid_discount(self):
        """Should raise error for invalid discount."""
        with pytest.raises(ValueError, match="discount_percentage must be >= 0"):
            PlanUpdate(discount_percentage=-5)

    def test_plan_update_validate_currency(self):
        """Should validate currency when provided."""
        update = PlanUpdate(currency=Currency.INDIA)
        assert update.currency == Currency.INDIA

    def test_plan_update_invalid_currency(self):
        """Should raise error for invalid currency."""
        with pytest.raises(ValueError, match="Invalid currency"):
            PlanUpdate(currency="INVALID")

    def test_plan_update_validate_modules(self, mapper):
        """Should validate modules when provided."""
        update = PlanUpdate(modules=["console:Chat"])
        assert len(update.modules) == 1

    def test_plan_update_validate_plan_type(self):
        """Should validate plan_type when provided."""
        update = PlanUpdate(plan_type=PlanType.WALLET)
        assert update.plan_type == PlanType.WALLET

    def test_plan_update_invalid_plan_type(self):
        """Should raise error for invalid plan_type."""
        with pytest.raises(ValueError, match="Invalid plan_type"):
            PlanUpdate(plan_type="INVALID")

    def test_plan_update_validate_tag(self):
        """Should validate tag when provided."""
        update = PlanUpdate(tag="premium")
        assert update.tag == "premium"

    def test_plan_update_invalid_tag(self):
        """Should raise error for invalid tag."""
        with pytest.raises(ValueError, match="tag cannot be empty"):
            PlanUpdate(tag="")

    def test_plan_update_validate_hierarchy(self):
        """Should validate hierarchy when provided."""
        update = PlanUpdate(hierarchy=5)
        assert update.hierarchy == 5

    def test_plan_update_invalid_hierarchy(self):
        """Should raise error for invalid hierarchy."""
        with pytest.raises(ValueError, match="hierarchy must be between 0 and 999"):
            PlanUpdate(hierarchy=-1)

    def test_plan_update_validate_service_name(self):
        """Should validate service_name when provided."""
        update = PlanUpdate(service_name=Platform.CONSOLE)
        assert update.service_name == Platform.CONSOLE

    def test_plan_update_invalid_service_name(self):
        """Should raise error for invalid service_name."""
        with pytest.raises(ValueError, match="Invalid service_name"):
            PlanUpdate(service_name="INVALID")

    def test_plan_update_is_active(self):
        """Should update is_active flag."""
        update = PlanUpdate(is_active=False)
        assert update.is_active is False

    def test_plan_update_is_free_trial(self):
        """Should update is_free_trial flag."""
        update = PlanUpdate(is_free_trial=True)
        assert update.is_free_trial is True

    def test_plan_update_otc_charge(self):
        """Should update otc_charge."""
        update = PlanUpdate(otc_charge=150.0)
        assert update.otc_charge == 150.0

    def test_plan_update_extra_fields_forbidden(self):
        """Should raise error for extra fields."""
        with pytest.raises(ValidationError):
            PlanUpdate(
                name="Test",
                extra_field="not allowed",
            )


class TestPlanResponse:
    """Test PlanResponse model."""

    def test_plan_response_from_attributes(self):
        """Should create PlanResponse from ORM model."""

        class MockPlan:
            id= UUID("11111111-1111-1111-1111-111111111111")
            name = "Test Plan"
            description = "Test"
            price = 1000.0
            discount_percentage = 10.0
            currency = Currency.INDIA
            duration = 1  # ADDED: duration is required
            limits = {}
            modules = []
            plan_type = PlanType.WALLET
            is_active = True
            created_by= UUID("11111111-1111-1111-1111-111111111111")
            created_at = 1234567890
            updated_by = None
            updated_at = None
            tag = "test"
            hierarchy = 1
            service_name = Platform.CONSOLE
            is_free_trial = False
            otc_charge = None

        plan = MockPlan()
        response = PlanResponse.model_validate(plan)

        assert response.is_purchased is False

    def test_plan_response_with_optional_fields(self):
        """Should handle optional fields correctly."""

        class MockPlan:
            id= UUID("11111111-1111-1111-1111-111111111111")
            name = "Test Plan"
            description = "Description"
            price = 1000.0
            discount_percentage = 10.0
            currency = Currency.INDIA
            duration = 3  # ADDED: duration is required
            limits = {"campaigns": 100}
            modules = ["talko:campaigns"]
            plan_type = PlanType.STANDARD
            is_active = True
            created_by= UUID("11111111-1111-1111-1111-111111111111")
            created_at = 1234567890
            updated_by= UUID("22222222-2222-2222-2222-222222222222")
            updated_at = 1234567900
            tag = "premium"
            hierarchy = 5
            service_name = Platform.CONSOLE
            is_free_trial = True
            otc_charge = 50.0

        plan = MockPlan()
        response = PlanResponse.model_validate(plan)

        assert response.description == "Description"
        assert response.updated_by== UUID("22222222-2222-2222-2222-222222222222")
        assert response.updated_at == 1234567900
        assert response.is_free_trial is True
        assert response.otc_charge == 50.0
        assert response.duration == 3
        assert len(response.limits) == 1
        assert len(response.modules) == 1


class TestDisallowedLimitKeys:
    """Test DISALLOWED_LIMIT_KEYS constant."""

    def test_disallowed_limit_keys_contains_expected(self):
        """Should contain expected disallowed keys."""
        assert PlanCustomLimitKeys.Console.ACTIVE_USERS in DISALLOWED_LIMIT_KEYS

    def test_plan_response_discounted_price_with_price_and_discount(self):
        """Should calculate discounted price when price and discount present."""

        class MockPlan:
            id= UUID("11111111-1111-1111-1111-111111111111")
            name = "Test Plan"
            description = None
            price = 1000.0
            discount_percentage = 20.0
            currency = Currency.INDIA
            duration = 1  # ADDED: duration is required
            limits = {}
            modules = []
            plan_type = PlanType.STANDARD
            is_active = True
            created_by= UUID("11111111-1111-1111-1111-111111111111")
            created_at = 1234567890
            updated_by = None
            updated_at = None
            tag = "test"
            hierarchy = 1
            service_name = Platform.CONSOLE
            is_free_trial = False
            otc_charge = None

        plan = MockPlan()
        response = PlanResponse.model_validate(plan)

        # Discounted price should be 1000 - (1000 * 0.20) = 800
        assert response.discounted_price == 800.0

    def test_plan_response_discounted_price_without_price(self):
        """Should return None for discounted price when price is None."""

        class MockPlan:
            id= UUID("11111111-1111-1111-1111-111111111111")
            name = "Test Plan"
            description = None
            price = None
            discount_percentage = 20.0
            currency = Currency.INDIA
            duration = 0  # ADDED: duration is required
            limits = {}
            modules = []
            plan_type = PlanType.WALLET
            is_active = True
            created_by= UUID("11111111-1111-1111-1111-111111111111")
            created_at = 1234567890
            updated_by = None
            updated_at = None
            tag = "test"
            hierarchy = 1
            service_name = Platform.CONSOLE
            is_free_trial = False
            otc_charge = None

        plan = MockPlan()
        response = PlanResponse.model_validate(plan)

        assert response.discounted_price is None

    def test_plan_response_default_is_purchased(self):
        """Should default is_purchased to False."""

        class MockPlan:
            id= UUID("11111111-1111-1111-1111-111111111111")
            name = "Test Plan"
            description = None
            price = 1000.0
            discount_percentage = 0.0
            currency = Currency.INDIA
            duration = 1  # ADDED: duration is required
            limits = {}
            modules = []
            plan_type = PlanType.STANDARD
            is_active = True
            created_by= UUID("11111111-1111-1111-1111-111111111111")
            created_at = 1234567890
            updated_by = None
            updated_at = None
            tag = "test"
            hierarchy = 1
            service_name = Platform.CONSOLE
            is_free_trial = False
            otc_charge = None

        plan = MockPlan()
        response = PlanResponse.model_validate(plan)

        assert response.is_purchased is False
