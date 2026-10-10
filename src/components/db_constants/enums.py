from enum import Enum

from sqlalchemy.orm import DeclarativeMeta

from src.components.db_constants import models


class ConstantsTypes(Enum):
    CONSTANTS = "Constants"
    DYNAMIC_VARIABLES = "DynamicVariables"
    MEDIA_CONSTANTS = "MediaConstants"
    GLOBAL_CONSTANTS = "GlobalConstants"
    GLOBAL_DYNAMIC_VARIABLES = "GlobalDynamicVariables"
    GLOBAL_MEDIA_CONSTANTS = "GlobalMediaConstants"

    @classmethod
    def get_db_constant_model(cls, constant_type: str) -> type[models.ConstantsBase]:
        """
        Get the model class dynamically based on the constant type string.
        """
        model_mapping = {
            cls.CONSTANTS.value: models.Constants,
            cls.DYNAMIC_VARIABLES.value: models.DynamicVariables,
            cls.MEDIA_CONSTANTS.value: models.MediaConstants,
            cls.GLOBAL_CONSTANTS.value: models.GlobalConstants,
            cls.GLOBAL_DYNAMIC_VARIABLES.value: models.GlobalDynamicVariables,
            cls.GLOBAL_MEDIA_CONSTANTS.value: models.GlobalMediaConstants,
        }

        return model_mapping[constant_type]
