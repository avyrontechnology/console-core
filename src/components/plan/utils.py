from typing import Optional

from src.components.plan.constants import PlanCustomLimitKeys


class PlanUtils:

    @staticmethod
    def split_modules_by_service(modules: list[str]) -> dict[str, list[str]]:
        """
        Example modules:
        ["console:dashboard", "console:analytics"]
        ->
        {
            "console": ["dashboard", "analytics"]
        }
        """
        if not modules:
            return {}

        grouped = {}
        for mod in modules:
            if ":" not in mod:
                continue
            service, module_name = mod.split(":", 1)
            grouped.setdefault(service, []).append(module_name)

        return grouped

    @staticmethod
    def split_limits_by_service(limits: dict) -> dict[str, dict]:
        """
        Split plan limits into service-wise buckets based on PlanCustomLimitKeys.

        Input limits are expected WITHOUT service prefixes.
        Service ownership is inferred by checking which service class
        in PlanCustomLimitKeys declares the given limit key.

        Example input:
        {
            "ACTIVE_USERS": 10,
            "VIEW_ANALYTICS": 1
        }

        Given PlanCustomLimitKeys:
            class Console:
                ACTIVE_USERS = "ACTIVE_USERS"

        Output:
        {
            "console": {
                "ACTIVE_USERS": 10
            }
        }

        Notes:
        - A single limit key MAY belong to multiple services.
        - In such cases, the limit is included under ALL applicable services.
        - Returned service names are lowercase class names from PlanCustomLimitKeys.
        - Unknown limit keys are silently ignored (schema validation handles them).

        :param limits: Dict of limit_name -> value (no service prefix)
        :return: Dict of service_name -> {limit_name -> value}
        """
        if not limits:
            return {}

        grouped: dict[str, dict] = {}

        for limit_key, value in limits.items():
            for service_cls in PlanCustomLimitKeys.__dict__.values():
                if not isinstance(service_cls, type):
                    continue

                if limit_key in service_cls.__dict__.values():
                    service_name = service_cls.__name__.lower()
                    grouped.setdefault(service_name, {})[limit_key] = value

        return grouped

    @staticmethod
    def calculate_discounted_price(
        price: Optional[float],
        discount_percentage: Optional[float],
    ) -> Optional[float]:
        if price is None:
            return None

        discount: float = discount_percentage or 0.0
        if discount <= 0:
            return round(price, 2)

        discounted_price: float = price - (price * discount / 100)
        return round(discounted_price, 2)
