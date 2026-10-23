from uuid import UUID
import re
from typing import Dict, List, Optional, Set, Union

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from src.components.plan.constants import PlanCustomLimitKeys, PlanType, Platform
from src.components.plan.mapper import SERVICE_FEATURE_MAPPER
from src.components.plan.utils import PlanUtils
from src.components.wallet.enum import Currency

DISALLOWED_LIMIT_KEYS: Set[str] = {
    PlanCustomLimitKeys.Console.ACTIVE_USERS,
}


class PlanValidationMixin:
    def _validate_name(self, name: str) -> str:
        if not name or not name.strip():
            raise ValueError("name cannot be empty")

        cleaned_name: str = name.strip()

        if len(cleaned_name) > 100:
            raise ValueError("name must be less than or equal to 100 characters")

        if not re.match(r"^[a-zA-Z0-9\s\-_]+$", cleaned_name):
            raise ValueError(
                "name can only contain alphanumeric characters, spaces, hyphens, and underscores"
            )

        return cleaned_name

    def _validate_tag(self, tag: str) -> str:
        if not tag or not tag.strip():
            raise ValueError("tag cannot be empty")

        cleaned_tag: str = tag.strip()

        if len(cleaned_tag) > 30:
            raise ValueError("tag must not exceed 30 characters")

        return cleaned_tag

    def _validate_hierarchy(self, hierarchy: int) -> int:
        if hierarchy is None:
            raise ValueError("hierarchy is required")

        if not isinstance(hierarchy, int):
            raise ValueError("hierarchy must be an integer")

        if hierarchy < 0 or hierarchy > 999:
            raise ValueError("hierarchy must be between 0 and 999")

        return hierarchy

    def _validate_duration(self, duration: int) -> int:
        if duration is None:
            return 0
        if duration < 0:
            raise ValueError("Duration cannot be negative")
        return duration

    def _validate_description(self, description: str) -> str:
        cleaned_description: str = description.strip()

        if len(cleaned_description) > 500:
            raise ValueError("description must be less than or equal to 500 characters")

        return cleaned_description

    def _validate_price(self, price: float) -> None:
        if price < 100:
            raise ValueError("price must be greater than 99")

        if price > 10_000_000_00:
            raise ValueError("price must be less than or equal to 1000000000")

        if round(price, 2) != price:
            raise ValueError("price must have at most two decimal places")

    def _validate_discount(self, discount_percentage: float) -> None:
        if discount_percentage < 0:
            raise ValueError("discount_percentage must be >= 0")

        if discount_percentage > 100:
            raise ValueError("discount_percentage must be <= 100")

        if round(discount_percentage, 2) != discount_percentage:
            raise ValueError("discount_percentage must have at most two decimal places")

    def _validate_currency(self, currency: str) -> None:
        allowed_currencies: Set[str] = {
            value
            for attribute_name, value in Currency.__dict__.items()
            if not attribute_name.startswith("_") and attribute_name.isupper()
        }

        if currency not in allowed_currencies:
            raise ValueError(
                f"Invalid currency '{currency}'. Allowed currencies are: "
                f"{', '.join(sorted(allowed_currencies))}"
            )

    def _validate_plan_type(self, plan_type: str) -> None:
        allowed_plan_types: Set[str] = {
            value
            for attribute_name, value in PlanType.__dict__.items()
            if not attribute_name.startswith("_") and attribute_name.isupper()
        }

        if plan_type not in allowed_plan_types:
            raise ValueError(
                f"Invalid plan_type '{plan_type}'. Allowed plan types are: "
                f"{', '.join(sorted(allowed_plan_types))}"
            )
        if plan_type == PlanType.STANDARD:
            if getattr(self, "price", None) is None:
                raise ValueError("price is required when plan_type is STANDARD")

    def _validate_service_name(self, service_name: str) -> str:
        allowed_services: Set[str] = {
            value for attr, value in Platform.__dict__.items() if attr.isupper()
        }

        if service_name not in allowed_services:
            raise ValueError(
                f"Invalid service_name '{service_name}'. Allowed services are: "
                f"{', '.join(sorted(allowed_services))}"
            )
        return service_name

    def _validate_limits(self, limits: Dict[str, Union[int, bool]]) -> None:
        all_limit_keys: Set[str] = {
            value
            for class_value in PlanCustomLimitKeys.__dict__.values()
            if isinstance(class_value, type)
            for attribute_name, value in class_value.__dict__.items()
            if attribute_name.isupper()
        }

        # Final allowed keys (exclude disallowed ones)
        allowed_limit_keys: Set[str] = all_limit_keys - DISALLOWED_LIMIT_KEYS

        for limit_key, limit_value in limits.items():
            if limit_key in DISALLOWED_LIMIT_KEYS:
                raise ValueError(
                    f"Limit key '{limit_key}' is not allowed to be configured"
                )
            if limit_key not in allowed_limit_keys:
                raise ValueError(
                    f"Invalid limit key '{limit_key}'. Allowed keys are: "
                    f"{', '.join(sorted(allowed_limit_keys))}"
                )

            if not isinstance(limit_value, int) or limit_value == 0:
                raise ValueError(
                    f"limit value for '{limit_key}' must be a positive/negative integer"
                )

    def _validate_modules(self, modules: List[str]) -> None:
        """
        Validates a list of modules in the format 'service:feature'.
        """
        allowed_services: Set[str] = set(SERVICE_FEATURE_MAPPER.keys())

        for raw_module in modules:
            service, feature_name = self._parse_module(raw_module)
            self._validate_service(service, raw_module, allowed_services)
            self._validate_feature_name(service, feature_name)

    def _parse_module(self, raw_module: str) -> tuple[str, str]:
        """
        Parses 'service:feature_name' and returns (service, feature_name)
        """
        if not isinstance(raw_module, str):
            raise ValueError(f"Module '{raw_module}' must be a string.")

        cleaned_raw: str = raw_module.strip()

        if cleaned_raw.count(":") != 1:
            raise ValueError(
                f"Module '{cleaned_raw}' must be in format 'service:feature_name'"
            )

        service, feature_name = (part.strip() for part in cleaned_raw.split(":", 1))

        if not service or not feature_name:
            raise ValueError(
                f"Module '{cleaned_raw}' must have non-empty service and feature name"
            )

        return service, feature_name

    def _validate_service(
        self,
        service: str,
        raw_module: str,
        allowed_services: Set[str],
    ) -> None:
        if service not in allowed_services:
            raise ValueError(
                f"Invalid service '{service}' in module '{raw_module}'. "
                f"Allowed: {', '.join(sorted(allowed_services))}"
            )

    def _validate_feature_name(self, service: str, feature_name: str) -> None:
        """
        Validates the feature_name exists in the given service.
        """
        allowed_features: Set[str] = self._get_allowed_features(service)

        if feature_name not in allowed_features:
            raise ValueError(
                f"Invalid feature '{feature_name}' for service {service}. "
            )

    def _get_allowed_features(self, service: str) -> Set[str]:
        """
        Returns all feature names for a service,
        replacing spaces with underscores.
        """
        allowed_features: Set[str] = set()

        service_modules = SERVICE_FEATURE_MAPPER.get(service)

        if not service_modules:
            return allowed_features

        for module_features in service_modules.values():
            if not isinstance(module_features, dict):
                continue

            for feature_name in module_features.keys():
                if isinstance(feature_name, str):
                    allowed_features.add(feature_name.replace(" ", "_"))

        return allowed_features


class PlanBase(BaseModel, PlanValidationMixin):
    name: str = Field(...)
    description: Optional[str] = None
    price: Optional[float] = None
    discount_percentage: Optional[float] = 0.0
    currency: str = Field(Currency.INDIA, min_length=2, max_length=4)
    duration: int
    # limits: Dict[str, Union[int, bool]] = Field(default_factory=dict)
    modules: List[str] = Field(default_factory=list)
    plan_type: Optional[str] = None
    tag: str
    hierarchy: int
    service_name: str
    is_free_trial: Optional[bool] = None
    otc_charge: Optional[float] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_all(self):
        self.name = self._validate_name(self.name)
        self.tag = self._validate_tag(self.tag)
        self.hierarchy = self._validate_hierarchy(self.hierarchy)
        self.service_name = self._validate_service_name(self.service_name)
        self.duration = self._validate_duration(self.duration)

        if not self.plan_type:
            raise ValueError("plan_type is required")

        if self.description is not None:
            self.description = self._validate_description(self.description)

        if self.price is not None:
            self._validate_price(self.price)

        if self.discount_percentage is not None:
            self._validate_discount(self.discount_percentage)

        self._validate_currency(self.currency)

        # if self.limits: # NOSONAR
        #     self._validate_limits(self.limits)

        if self.modules:
            self._validate_modules(self.modules)

        if self.plan_type is not None:
            self._validate_plan_type(self.plan_type)

        return self


class PlanUpdate(BaseModel, PlanValidationMixin):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    discount_percentage: Optional[float] = None
    currency: Optional[str] = None
    duration: Optional[int] = None
    # limits: Optional[Dict[str, Union[int, bool]]] = None
    modules: Optional[List[str]] = None
    plan_type: Optional[str] = None
    is_active: Optional[bool] = None
    tag: Optional[str] = None
    hierarchy: Optional[int] = None
    service_name: Optional[str] = None
    is_free_trial: Optional[bool] = None
    otc_charge: Optional[float] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_partial(self):
        if self.name is not None:
            self.name = self._validate_name(self.name)

        if self.description is not None:
            self.description = self._validate_description(self.description)

        if self.price is not None:
            self._validate_price(self.price)

        if self.discount_percentage is not None:
            self._validate_discount(self.discount_percentage)

        if self.currency is not None:
            self._validate_currency(self.currency)

        # if self.limits is not None: # NOSONAR
        #     self._validate_limits(self.limits)

        if self.modules is not None:
            self._validate_modules(self.modules)

        if self.plan_type is not None:
            self._validate_plan_type(self.plan_type)

        if self.tag is not None:
            self._validate_tag(self.tag)

        if self.hierarchy is not None:
            self._validate_hierarchy(self.hierarchy)

        if self.service_name is not None:
            self._validate_service_name(self.service_name)

        if self.duration is not None:
            self._validate_duration(self.duration)
        return self


class PlanResponse(BaseModel):
    """Schema used only for API responses."""

    id: UUID
    name: str
    description: Optional[str]
    price: Optional[float]
    discount_percentage: Optional[float]
    currency: str
    duration: int
    limits: Dict[str, Union[int, bool]]
    modules: List[str]
    plan_type: str
    is_active: bool
    created_by: UUID
    created_at: int
    updated_by: Optional[UUID]
    updated_at: Optional[int]
    is_purchased: bool = False
    tag: str
    hierarchy: int
    service_name: str
    is_free_trial: Optional[bool] = False
    otc_charge: Optional[float]

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def discounted_price(self) -> Optional[float]:
        return PlanUtils.calculate_discounted_price(
            self.price,
            self.discount_percentage,
        )
