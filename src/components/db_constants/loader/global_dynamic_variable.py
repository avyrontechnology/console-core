# After adding a constant here, make sure to add the same in src.components.db_constants.mapper in their respective model.

from enum import Enum

from sqlalchemy import select

from src.components.db_constants.models import GlobalDynamicVariables
from src.main import session_factory


class GlobalDynamicVariableEnum(Enum):
    pass


async def fetch_global_dynamic_variable(key: str) -> str:
    """
    Fetch the global dynamic variable from the database based on the key.

    Args:
        key (str): The key of the dynamic variable to fetch.

    Returns:
        str: The value of the dynamic variable if found, otherwise None.
    """
    try:
        async with session_factory() as session:
            query = select(GlobalDynamicVariables).filter_by(name=key)
            result = await session.execute(query)
            global_dynamic_variable = result.scalars().first()

            if not global_dynamic_variable:
                raise ValueError(f"Global Dynamic variable with key '{key}' not found.")

            return global_dynamic_variable.value
    except Exception as e:
        print(f"Error fetching global dynamic variable for key '{key}': {e}")
        raise e


# Example usage:
# from src.components.db_constants.loader.dynamic_variable import fetch_global_dynamic_variable, GlobalDynamicVariableEnum
# value = await fetch_global_dynamic_variable(GlobalDynamicVariableEnum.CONSTANT_4.value)
# print(value)
