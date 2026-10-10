from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.components.db_constants.mapper import CONSTANT_KEY_TO_MODEL_MAPPER
from src.components.db_constants.models import (
    Constants,
    GlobalConstants,
    GlobalMediaConstants,
    MediaConstants,
)
from src.components.digital_assets.services import StorageHelper

constant_dict = {}
media_constants_dict = {}
global_constants_dict = {}
global_media_constants_dict = {}


class ConstantsInitializer:
    """
    A class to initialize constants by loading them from the database.
    """

    @classmethod
    async def _load_constants(cls, session_factory, model_class, target_dict):
        """
        Load constants from the database into the provided dictionary.
        """
        async with session_factory() as session:
            query = select(model_class)

            media_model = model_class in [MediaConstants, GlobalMediaConstants]
            if media_model:
                query = query.options(joinedload(model_class.media))

            result = await session.execute(query)

            constants = result.scalars().all()

            for constant in constants:
                if media_model and constant.media:
                    target_dict[constant.name] = constant.media.name
                else:
                    target_dict[constant.name] = constant.value

    @classmethod
    async def initialize_constants(cls, session):
        """
        Initializes all constants and loads them into memory.
        """
        await cls._load_constants(session, Constants, constant_dict)
        await cls._load_constants(session, MediaConstants, media_constants_dict)
        await cls._load_constants(session, GlobalConstants, global_constants_dict)
        await cls._load_constants(
            session, GlobalMediaConstants, global_media_constants_dict
        )

        print("All constants have been initialized.")


class ConstantsCreator:
    """
    A class to create constants in the database, ensuring no duplicates are added.
    """

    @classmethod
    async def _process_constants(
        cls, session, key_names, model, created_constants, existing_constants
    ):
        """
        Process constants for a specific model, checking for existence and creating new ones if needed.
        """
        for key_name in key_names:
            if await cls._constant_exists(session, key_name, model):
                existing_constants.append(
                    f'Already exists "{key_name}" in "{model.__name__}".'
                )
            else:
                await cls._create_new_constant(
                    session, key_name, model, created_constants
                )

    @classmethod
    async def _constant_exists(cls, session, key_name, model):
        """
        Check if a constant with the given key name exists in the database.
        """
        existing_constants_query = await session.execute(
            select(model).filter(model.name == key_name)
        )
        return existing_constants_query.scalars().first() is not None

    @classmethod
    async def _create_new_constant(cls, session, key_name, model, created_constants):
        """
        Create a new constant in the database.
        """
        value = None if model in [MediaConstants, GlobalMediaConstants] else ""
        new_constant = model(name=key_name, value=value)
        session.add(new_constant)
        await session.commit()
        created_constants.append(f"Created {key_name} in {model.__name__}.")

    @classmethod
    def _print_report(cls, created_constants, existing_constants):
        """
        Print a report of created and existing constants.
        """
        print("\n---------------------------- Constants Creation Report ----------------------------")

        if created_constants:
            print("\nCreated Constants:")
            for created in created_constants:
                print(f"- {created}")
        else:
            print("No constants were created.")

        if existing_constants:
            print("\nAlready Existing Constants:")
            for existing in existing_constants:
                print(f"- {existing}")
        else:
            print("All constants were already present.")

        print(
            "\n-----------------------------------------------------------------------------------"
        )

    @classmethod
    async def create_constants(cls, session_factory):
        """
        Function to create constants in the database, ensuring no duplicates are added.
        """

        created_constants = []
        existing_constants = []

        async with session_factory() as session:
            for key_names, model in CONSTANT_KEY_TO_MODEL_MAPPER:
                await cls._process_constants(
                    session, key_names, model, created_constants, existing_constants
                )

        cls._print_report(created_constants, existing_constants)


class LazyConstantLoader:
    """
    A class to lazily fetch constants either from a dictionary or generate a pre-signed URL using a model.
    If both a dictionary and model are provided, the class will first check the dictionary, then use the model.
    """

    def __init__(self, key, dict=None, model=None, default=None):
        """
        Initialize the LazyConstantLoader.

        :param key: The key to look up.
        :param dictionary: The dictionary to fetch the constant from (optional).
        :param model: The model to fetch the constant from (optional).
        :param default: The default value to return if the key is not found.
        """

        self.key = key
        self.dictionary = dict
        self.model = model
        self.default = default

    def __repr__(self):
        """
        Fetch the value lazily from the dictionary first. If not found and model is provided,
        generate and return the pre-signed URL using the model.
        """

        if self.model:
            value = StorageHelper.get_presigned_url(self.key)
        else:
            value = self.dictionary.get(self.key, self.default)

        return str(value if value not in (None, "") else self.default)
