from abc import ABC, abstractmethod


class BaseStorageManager(ABC):
    """
    Abstract base class for managing file storage operations.
    """

    @abstractmethod
    def get_presigned_url(
        self, file_name: str, view_only: bool = False, is_public: bool = False
    ) -> str:
        """
        Returns a URL for accessing a file in storage.
        - If public: returns a permanent public URL (never expires).
        - If private: returns a presigned URL (expires after URL_EXPIRATION_TIME).

        Args:
            file_name (str): The name of the file in storage.
            view_only (bool): If False (default), file is downloaded as attachment.
                              If True, file is viewed inline in browser.
            is_public (bool): If True, returns permanent public URL.
                              If False, returns expiring presigned URL.
        """
        pass

    @abstractmethod
    async def upload_digital_asset(
        self,
        file: object,
        file_path: str,
        is_public: bool = False,
        view_only: bool = False,
    ) -> str:
        """
        Uploads a digital asset to the storage.

        Args:
            file (object): The file object to upload.
            file_path (str): The path where the file will be stored.
            is_public (bool): If True, file is uploaded with public-read ACL,
                              returns permanent URL.
                              If False, file is uploaded privately,
                              returns presigned URL.
            view_only (bool): If False (default), file is downloaded as attachment.
                              If True, file is viewed inline in browser.
        """
        pass

    @abstractmethod
    def delete_digital_asset(self, file_path: str) -> None:
        """
        Deletes a digital asset from the storage.

        Args:
            file_path (str): The path of the file to delete.
        """
        pass
