import mimetypes

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
from src.components.digital_assets import constants
from src.components.digital_assets.logger_adapter import LoggerAdapter
from src.components.digital_assets.messages import NO_CRED_FOUND_DO
from src.components.digital_assets.storage.base import BaseStorageManager
from src.core.environment import ENV

logger = LoggerAdapter().get_logger()


class DOStorageManager(BaseStorageManager):
    """
    Storage manager for DigitalOcean Space.
    """

    def __init__(self):
        self.endpoint_url = ENV.DO_ENDPOINT_URL
        self.space_name = ENV.DO_SPACE_NAME
        self.secret_access_key = ENV.DO_SECRET_ACCESS_KEY
        self.access_key_id = ENV.DO_ACCESS_KEY_ID
        self.env = ENV.ENVIRONMENT

        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            endpoint_url=self.endpoint_url,
            config=Config(signature_version="s3v4"),
        )
        logger.info("DOStorageManager initialized with endpoint: %s", self.endpoint_url)

    def get_presigned_url(
        self, file_path: str, view_only: bool = False, is_public: bool = False
    ) -> str:
        """
        Returns a URL for a file stored in DigitalOcean Spaces.
        - If public: returns a permanent public URL (never expires).
        - If private: returns a presigned URL (expires after URL_EXPIRATION_TIME).

        Args:
            file_path (str): The path of the file in the Space.
            view_only (bool): If False (default), file is downloaded as attachment.
                              If True, file is viewed inline in browser.
                              For public files, this is controlled at upload time via ContentDisposition.
            is_public (bool): If True, returns permanent public URL.
                              If False, returns expiring presigned URL.

        Returns:
            str: Permanent public URL or expiring presigned URL.

        Raises:
            RuntimeError: If credentials are missing or URL generation fails (private only).
        """
        if is_public:
            public_url = f"{self.endpoint_url}/{self.space_name}/{file_path}"
            logger.info("Returning permanent public URL for file: %s", file_path)
            return public_url

        try:
            logger.info("Generating presigned URL for file: %s", file_path)
            content_disposition = "inline" if view_only else "attachment"
            presigned_url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.space_name,
                    "Key": file_path,
                    "ResponseContentDisposition": content_disposition,
                },
                ExpiresIn=constants.URL_EXPIRATION_TIME,
            )
            logger.info("Successfully generated presigned URL for file: %s", file_path)
            return presigned_url

        except NoCredentialsError:
            logger.error(NO_CRED_FOUND_DO)
            raise RuntimeError(NO_CRED_FOUND_DO)

        except ClientError as e:
            logger.error(
                "Failed to generate presigned URL for file %s: %s", file_path, e
            )
            raise RuntimeError(f"Failed to generate presigned URL: {e}")

    async def upload_digital_asset(
        self, file_obj, file_path: str, is_public: bool = False, view_only: bool = False
    ) -> str:
        """
        Uploads a digital asset (file) to DigitalOcean Spaces.

        Args:
            file_obj (file-like object): The file object to upload.
            file_path (str): The path where the file will be stored in the Space.
            is_public (bool): If True, file is uploaded with public-read ACL,
                              returns permanent public URL.
                              If False, file is uploaded privately,
                              returns presigned URL.
            view_only (bool): If False (default), file is downloaded as attachment.
                              If True, file is viewed inline in browser.

        Returns:
            str: Permanent public URL (if public) or presigned URL (if private).

        Raises:
            ValueError: If the upload fails.
        """
        try:
            logger.info(
                "Uploading file '%s' to DigitalOcean Space at path: %s (public: %s, view_only: %s)",
                file_obj.filename,
                file_path,
                is_public,
                view_only,
            )
            content_type, _ = mimetypes.guess_type(file_obj.filename)
            content_type = content_type or "application/octet-stream"

            content_disposition = "inline" if view_only else "attachment"
            extra_args = {
                "ContentType": content_type,
                "ContentDisposition": content_disposition,
            }
            if is_public:
                extra_args["ACL"] = "public-read"

            self.s3_client.upload_fileobj(
                file_obj.file,
                self.space_name,
                file_path,
                ExtraArgs=extra_args,
            )
            logger.info(
                "Successfully uploaded file '%s' to path: %s",
                file_obj.filename,
                file_path,
            )

            return self.get_presigned_url(
                file_path, view_only=view_only, is_public=is_public
            )

        except ClientError as e:
            logger.error(
                "Failed to upload file '%s' to path '%s': %s",
                file_obj.filename,
                file_path,
                e.response["Error"]["Message"],
            )
            raise ValueError(
                f"Failed to upload file '{file_path}': {e.response['Error']['Message']}"
            )
        except Exception as e:
            logger.error(
                "An error occurred while uploading file '%s' to path '%s': %s",
                file_obj.filename,
                file_path,
                str(e),
            )
            raise ValueError(
                f"An error occurred while uploading file '{file_path}': {str(e)}"
            )

    def delete_digital_asset(self, file_path: str) -> None:
        """
        Deletes a digital asset (file) from DigitalOcean Spaces.

        Args:
            file_path (str): The path of the file to delete in the Space.

        Raises:
            RuntimeError: If credentials are missing or the deletion fails.
        """
        try:
            logger.info("Deleting file from DigitalOcean Space at path: %s", file_path)
            self.s3_client.delete_object(Bucket=self.space_name, Key=file_path)
            logger.info("Successfully deleted file at path: %s", file_path)

        except NoCredentialsError:
            logger.error(NO_CRED_FOUND_DO)
            raise RuntimeError(NO_CRED_FOUND_DO)

        except ClientError as e:
            logger.error("Failed to delete file at path %s: %s", file_path, e)
            raise RuntimeError(f"Failed to delete file '{file_path}': {e}")
