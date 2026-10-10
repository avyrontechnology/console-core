import pytest
from sqlalchemy import Column, Integer, String, Boolean, create_engine, select, func
from sqlalchemy.orm import declarative_base, Session
from src.components.filters.criteria import BaseFilterCriteria
from src.components.filters.constants import BuilderExceptionMessage, FilterKeys
from src.components.filters.builder import BaseFilterBuilder
from src.exceptions import UserException

Base = declarative_base()

class TestModel(Base):
    __tablename__ = "test_table"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    age = Column(Integer)
    is_active = Column(Boolean)

@pytest.fixture
def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine

def test_resolve_field_from_models():
    builder = BaseFilterBuilder(
        models=[TestModel],
        criteria=BaseFilterCriteria(),
        base_query=select(TestModel)
    )
    assert builder._resolve_field_from_models("name") == TestModel.name
    with pytest.raises(AttributeError):
        builder._resolve_field_from_models("not_a_field")

def test_cast_filter_value_int_and_bool():
    builder = BaseFilterBuilder(
        models=[TestModel],
        criteria=BaseFilterCriteria(),
        base_query=select(TestModel)
    )

    # Integer should work fine
    assert builder._cast_filter_value("5", "=", Integer()) == 5

    # Boolean: real bools pass through
    assert builder._cast_filter_value(True, "=", Boolean()) is True
    assert builder._cast_filter_value(False, "=", Boolean()) is False

    # The status filter arrives from the UI as text, so the common string
    # forms are coerced rather than rejected.
    assert builder._cast_filter_value("true", "=", Boolean()) is True
    assert builder._cast_filter_value("false", "=", Boolean()) is False
    assert builder._cast_filter_value("Active", "=", Boolean()) is True
    assert builder._cast_filter_value("Inactive", "=", Boolean()) is False

    # Anything that is not a recognised boolean form still raises.
    with pytest.raises(UserException):
        builder._cast_filter_value("not_bool", "=", Boolean())
    with pytest.raises(UserException):
        builder._cast_filter_value("2", "=", Boolean())

def test_build_operator_condition_eq_like_in_between():
    builder = BaseFilterBuilder(
        models=[TestModel],
        criteria=BaseFilterCriteria(),
        base_query=select(TestModel)
    )
    # "=" operator
    cond = builder._build_operator_condition("=", TestModel.name, "john", String())
    assert str(cond) == "lower(test_table.name) = :lower_1"
    # "LIKE" operator
    cond = builder._build_operator_condition("LIKE", TestModel.name, "john", String())
    assert str(cond).startswith("lower(test_table.name) LIKE")
    # "IN" operator
    cond = builder._build_operator_condition("IN", TestModel.name, ["john", "doe"], String())
    assert "IN" in str(cond)
    # "BETWEEN" operator
    cond = builder._build_operator_condition("BETWEEN", TestModel.age, [18, 30], Integer())
    assert "test_table.age >= :age_1 AND test_table.age <= :age_2" in str(cond)
    # Unsupported operator
    with pytest.raises(ValueError):
        builder._build_operator_condition("UNSUPPORTED", TestModel.name, "john", String())

def test_apply_group_by_fields():
    criteria = BaseFilterCriteria()
    criteria.group_by = ["age", "is_active"]
    builder = BaseFilterBuilder(
        models=[TestModel],
        criteria=criteria,
        base_query=select(TestModel)
    )
    query = builder._apply_group_by_fields(select(TestModel))
    assert "GROUP BY" in str(query)

def test_apply_aggregations():
    criteria = BaseFilterCriteria()
    criteria.aggregations = [{"function": "count", "field": "id"}]
    builder = BaseFilterBuilder(
        models=[TestModel],
        criteria=criteria,
        base_query=select(TestModel)
    )
    query = builder._apply_aggregations(select(TestModel))
    assert "count(test_table.id)" in str(query)

def test_apply_ordering():
    criteria = BaseFilterCriteria()
    criteria.order_by = [{"field": "age", "direction": "DESC"}]
    builder = BaseFilterBuilder(
        models=[TestModel],
        criteria=criteria,
        base_query=select(TestModel)
    )
    query = builder._apply_ordering(select(TestModel))
    assert "ORDER BY" in str(query)

@pytest.mark.asyncio
async def test_build_query_full(setup_db):
    criteria = BaseFilterCriteria()
    criteria.filters = [
        {FilterKeys.FIELD: "is_active", FilterKeys.OPERATOR: "=", FilterKeys.VALUE: True},
        {FilterKeys.FIELD: "age", FilterKeys.OPERATOR: ">=", FilterKeys.VALUE: "18"},
    ]
    criteria.order_by = [{"field": "age", "direction": "ASC"}]
    criteria.group_by = ["is_active"]
    criteria.aggregations = [{"function": "count", "field": "id"}]

    builder = BaseFilterBuilder(
        models=[TestModel],
        criteria=criteria,
        base_query=select(TestModel)
    )
    query = await builder.build_query()
    sql = str(query)

    assert "WHERE" in sql
    assert "GROUP BY" in sql
    assert "ORDER BY" in sql
    assert "count(test_table.id)" in sql