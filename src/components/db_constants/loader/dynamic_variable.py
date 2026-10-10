# After adding a constant here, make sure to add the same in src.components.db_constants.mapper in their respective model.

from enum import Enum

from sqlalchemy import select

from src.components.db_constants.models import DynamicVariables
from src.main import session_factory


class DynamicVariableEnum(Enum):
    pass


async def fetch_dynamic_variable(key: str) -> str:
    """
    Fetch the dynamic variable from the database based on the key.

    Args:
        key (str): The key of the dynamic variable to fetch.

    Returns:
        str: The value of the dynamic variable if found, otherwise None.
    """
    try:
        async with session_factory() as session:
            query = select(DynamicVariables).filter_by(name=key)
            result = await session.execute(query)
            dynamic_variable = result.scalars().first()

            if not dynamic_variable:
                raise ValueError(f"Dynamic variable with key '{key}' not found.")

            return dynamic_variable.value
    except Exception as e:
        print(f"Error fetching dynamic variable for key '{key}': {e}")
        raise


# Example usage:
# from src.components.db_constants.loader.dynamic_variable import fetch_dynamic_variable, DynamicVariableEnum
# value = await fetch_dynamic_variable(DynamicVariableEnum.SAMPLE_DYNAMIC_VARIABLE.value)
# print(value)
