from fastapi import UploadFile
from src.components.digital_assets.logger_adapter import LoggerAdapter
from src.components.digital_assets.storage.factory import FactoryStorageManager
from src.core.environment import ENV

logger = LoggerAdapter().get_logger()


class StorageHelper:
    """
    Helper class to interact with various storage providers.
    """

    @staticmethod
    def _get_storage_manager():
        """Returns the appropriate storage manager based on the provider."""
        provider = ENV.STORAGE_SERVICE_PROVIDER
        if not provider:
            raise ValueError("STORAGE_SERVICE_PROVIDER is not set.")
        logger.info("Using storage provider: {}".format(provider))
        return FactoryStorageManager.get_storage_class(provider)

    @staticmethod
    def get_presigned_url(
        file_name: str, view_only: bool = False, is_public: bool = False
    ) -> str:
        """
        Fetches a URL from the storage manager.

        Args:
            file_name (str): The name of the file in storage.
            view_only (bool): If False (default), file is downloaded as attachment.
                              If True, file is viewed inline in browser.
                              Ignored for public files (controlled at upload time).
            is_public (bool): If True, returns permanent public URL.
                              If False, returns expiring presigned URL.
        """
        storage_class = StorageHelper._get_storage_manager()
        return storage_class.get_presigned_url(file_name, view_only, is_public)

    @staticmethod
    async def upload_file(
        file_obj: UploadFile,
        file_path: str,
        is_public: bool = False,
        view_only: bool = False,
    ) -> str:
        """
        Uploads a file to the storage provider.

        Args:
            file_obj (UploadFile): The file object to upload.
            file_path (str): The path where the file will be stored.
            is_public (bool): If True, uploaded with public-read ACL, returns permanent URL.
                              If False, uploaded privately, returns presigned URL.
            view_only (bool): If False (default), file is downloaded as attachment.
                              If True, file is viewed inline in browser.
        """
        storage_class = StorageHelper._get_storage_manager()
        return await storage_class.upload_digital_asset(
            file_obj, file_path, is_public, view_only
        )

    @staticmethod
    async def delete_file(file_path: str) -> None:
        """
        Deletes a file from the storage provider.

        Args:
            file_path (str): The path of the file to delete.
        """
        storage_class = StorageHelper._get_storage_manager()
        return await storage_class.delete_digital_asset(file_path)
