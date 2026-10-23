from src.components.plan.utils import PlanUtils


class TestPlanUtils:
    # -------------------------------------------------------------------------
    # split_modules_by_service
    # -------------------------------------------------------------------------
    def test_split_modules_by_service_basic(self):
        modules = ["console:dashboard", "console:analytics", "talko:boards"]
        expected = {"console": ["dashboard", "analytics"], "talko": ["boards"]}
        assert PlanUtils.split_modules_by_service(modules) == expected

    def test_split_modules_by_service_empty_list(self):
        assert PlanUtils.split_modules_by_service([]) == {}

    def test_split_modules_by_service_invalid_format(self):
        modules = ["console-dashboard", "invalid", "talko:boards"]
        expected = {"talko": ["boards"]}
        assert PlanUtils.split_modules_by_service(modules) == expected

    def test_split_modules_by_service_multiple_services(self):
        modules = ["a:one", "b:two", "a:three", "c:four"]
        expected = {"a": ["one", "three"], "b": ["two"], "c": ["four"]}
        assert PlanUtils.split_modules_by_service(modules) == expected

    # -------------------------------------------------------------------------
    # split_limits_by_service
    # -------------------------------------------------------------------------

    def test_split_limits_by_service_empty_dict(self):
        assert PlanUtils.split_limits_by_service({}) == {}

    def test_split_limits_by_service_basic(self):
        limits = {"ACTIVE_USERS": 5}

        expected = {"console": {"ACTIVE_USERS": 5}}

        assert PlanUtils.split_limits_by_service(limits) == expected

    def test_split_limits_by_service_invalid_keys(self):
        limits = {"UNKNOWN_LIMIT": 10, "ACTIVE_USERS": 3}

        expected = {"console": {"ACTIVE_USERS": 3}}

        assert PlanUtils.split_limits_by_service(limits) == expected

    def test_split_limits_by_service_multiple_per_service(self):
        limits = {"ACTIVE_USERS": 10}

        expected = {"console": {"ACTIVE_USERS": 10}}

        assert PlanUtils.split_limits_by_service(limits) == expected
