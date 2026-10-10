from src.components.digital_assets.constants import StorageProvidersEnum
from src.components.digital_assets.storage.base import BaseStorageManager
from src.components.digital_assets.storage.managers import digital_ocean_manager


class FactoryStorageManager:
    """
    Factory class to get the appropriate storage manager based on the provider.
    """

    @staticmethod
    def get_storage_class(provider: str) -> BaseStorageManager:
        """
        Returns the appropriate storage manager based on the provider.

        Args:
            provider (str): The name of the storage provider.

        Returns:
            BaseStorageManager: An instance of the storage manager for the given provider.

        Raises:
            ValueError: If the provider is not found in the mapping.
        """
        if provider == StorageProvidersEnum.DIGITAL_OCEAN.name:
            storage_manager_class = digital_ocean_manager.DOStorageManager()
        # elif provider == StorageProvidersEnum.AWS.name:
        #     storage_manager_class = AWSStorageManager()
        # elif provider == StorageProvidersEnum.AZURE.name:
        #     storage_manager_class = BlobStorageManager()
        else:
            raise ValueError("Unknown storage service provider: {}".format(provider))
        return storage_manager_class
