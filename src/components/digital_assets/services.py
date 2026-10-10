import uuid
from typing import List

from fastapi import HTTPException
from src.components.digital_assets.constants import DigitalAssetEnum
from src.components.digital_assets.logger_adapter import LoggerAdapter
from src.components.digital_assets.models import DigitalAssets
from src.components.digital_assets.repositories import DigitalAssetRepository
from src.components.digital_assets.schema import (
    DigitalAssetResponse,
    UploadDigitalAssetResponse,
)
from src.components.digital_assets.storage.helper import StorageHelper
from src.components.digital_assets.utils import DigitalAssetUtils
from src.core.environment import ENV

logger = LoggerAdapter().get_logger()


class DigitalAssetService:
    def __init__(self, digital_asset_repository: DigitalAssetRepository):
        """
        Initialize the DigitalAssetService.

        Args:
            digital_asset_repository (DigitalAssetRepository): The repository for digital asset operations.
            logger: The logger instance for logging service operations.
        """
        self.__digital_asset_repository = digital_asset_repository

    async def get_digital_asset_details(
        self, partner_id: int, asset_type: str
    ) -> DigitalAssetResponse:
        """
        Fetch the details of a digital asset by its ID and Type.

        Args:
            asset_unique_id (int): The ID of the digital asset to retrieve.
            asset_type (str): The Type of the digital asset to retrieve.

        Returns:
            DigitalAssetResponse: The response schema containing digital asset details.

        Raises:
            ValueError: If the digital asset is not found.
            Exception: For other unexpected errors.
        """
        try:
            logger.info(
                "Trying to fetch the digital asset details for partner_id: {}, asset_type: {}".format(
                    partner_id, asset_type
                )
            )
            if not DigitalAssetUtils.is_valid_asset_type(asset_type):
                raise HTTPException(
                    status_code=404,
                    detail=f"Invalid asset type. Valid types are: {[item.name for item in DigitalAssetEnum]}",
                )
            asset = (
                await self.__digital_asset_repository.get_digital_asset_by_partner_id(
                    partner_id, asset_type
                )
            )

            if not asset:
                logger.error(
                    "Digital asset not found for partner_id {}".format(partner_id)
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Digital asset with ID {partner_id} not found",
                )

            asset_url = StorageHelper.get_presigned_url(asset.name)

            result = DigitalAssetResponse(
                id=asset.id,
                name=asset.name,
                partner_id=asset.partner_id,
                version=asset.version,
                url=asset_url,
                asset_type=asset.asset_type,
                additional_info=asset.additional_info,
                created_by=asset.created_by,
                updated_by=asset.updated_by,
            )
            return result

        except Exception as e:
            logger.error(
                "An unexpected error occurred while fetching digital asset details for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise e

    async def get_digital_asset_by_id(
        self, digital_asset_id: int
    ) -> DigitalAssetResponse:
        """
        Fetch a digital asset by its ID.
        Args:
            digital_asset_id (int): The ID of the digital asset to fetch.
        Returns:
            DigitalAssetResponse: The response schema containing digital asset details.
        Raises:
            HTTPException: If the digital asset is not found.
            Exception: For other unexpected errors.
        """
        try:
            logger.info(f"Fetching digital asset with ID: {digital_asset_id}")
            asset = await self.__digital_asset_repository.get_digital_asset_by_id(
                digital_asset_id
            )

            if not asset:
                logger.error(f"Digital asset with ID {digital_asset_id} not found")
                raise HTTPException(
                    status_code=404,
                    detail=f"Digital asset with ID {digital_asset_id} not found",
                )

            asset_url = StorageHelper.get_presigned_url(asset.name)

            result = DigitalAssetResponse(
                id=asset.id,
                name=asset.name,
                partner_id=asset.partner_id,
                version=asset.version,
                url=asset_url,
                asset_type=asset.asset_type,
                additional_info=asset.additional_info,
                created_by=asset.created_by,
                updated_by=asset.updated_by,
            )
            return result

        except Exception as e:
            logger.error(
                f"An unexpected error occurred while fetching digital asset with ID {digital_asset_id}: {str(e)}"
            )
            raise e

    async def create_digital_asset(
        self, partner_id: int, asset_type: str, input_file: object, user_id: int
    ) -> UploadDigitalAssetResponse:
        """
        Create a digital asset and upload it to cloud storage.

        Args:
            partner_id (int): ID of the partner uploading the asset.
            asset_type (str): Type of the digital asset (e.g., image, video).
            input_file (UploadFile): The file to be uploaded.
            user_id (int): ID of the user uploading the asset.

        Returns:
            DigitalAssetResponse: Contains the file name and URL of the uploaded asset.

        Raises:
            ValueError: Raised for invalid input values.
            Exception: Raised for other unexpected errors.
        """
        try:
            logger.info(
                "Trying to fetch the digital asset details for partner_id: {}, asset_type: {}".format(
                    partner_id, asset_type
                )
            )
            if not DigitalAssetUtils.is_valid_asset_type(asset_type):
                raise HTTPException(
                    status_code=404,
                    detail=f"Invalid asset type. Valid types are: {[item.name for item in DigitalAssetEnum]}",
                )

            file_name = f"{uuid.uuid4().hex}.{input_file.filename.split('.')[-1]}"
            file_path = f"{ENV.ENVIRONMENT}/{partner_id}/{ENV.SERVICE_NAME}/{asset_type}/{file_name}"

            logger.info(
                "Uploading file: {} to path: {}".format(input_file.filename, file_path)
            )
            await StorageHelper.upload_file(input_file, file_path)

            uploaded_url = StorageHelper.get_presigned_url(file_path)

            logger.info(
                "File uploaded successfully. File name: {}, URL: {}".format(
                    file_name, uploaded_url
                )
            )
            new_asset = await self.__digital_asset_repository.create_digital_asset(
                partner_id, asset_type, file_path, user_id
            )

            if not new_asset:
                logger.error(
                    "Digital asset not found for partner_id {}".format(partner_id)
                )
                raise HTTPException(
                    status_code=404,
                    detail="Digital asset with ID {} not created".format(partner_id),
                )

            result = UploadDigitalAssetResponse(
                id=new_asset.id, file_name=new_asset.name, url=uploaded_url
            )
            return result

        except Exception as e:
            logger.exception(
                "Unexpected error while creating digital asset: {error}".format(
                    error=str(e)
                )
            )
            raise e

    async def delete_digital_asset_by_id(self, digital_asset_id: int):
        """
        Delete a digital asset by its ID from both cloud storage and the database.

        Args:
            digital_asset_id (int): The ID of the digital asset to delete.

        Raises:
            HTTPException: If the asset is not found.
            Exception: For other unexpected errors.
        """
        try:
            logger.info(f"Deleting digital asset with ID: {digital_asset_id}")
            asset: DigitalAssets = await self.get_digital_asset_by_id(digital_asset_id)

            if not asset:
                logger.error(f"Digital asset with ID {digital_asset_id} not found")
                raise HTTPException(
                    status_code=404,
                    detail=f"Digital asset with ID {digital_asset_id} not found",
                )

            StorageHelper.delete_file(asset.name)
            logger.info(
                f"Digital asset with ID {digital_asset_id} deleted from cloud storage"
            )

            deleted = await self.__digital_asset_repository.delete_digital_asset_by_id(
                digital_asset_id
            )

            if not deleted:
                logger.error(
                    f"Failed to delete digital asset with ID {digital_asset_id}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete digital asset with ID {digital_asset_id}",
                )

            logger.info(
                f"Digital asset with ID {digital_asset_id} deleted successfully"
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while deleting digital asset with ID {digital_asset_id}: {str(e)}"
            )
            raise e

    async def get_digital_assets_by_digital_asset_ids(
        self, digital_asset_ids: list[str]
    ) -> list[DigitalAssetResponse]:
        """
        Fetch multiple digital assets by their IDs.

        Args:
            digital_asset_ids (list[str]): List of digital asset IDs to fetch.

        Returns:
            list[DigitalAssetResponse]: List of DigitalAssetResponse objects containing details of the fetched assets.

        Raises:
            HTTPException: If any asset is not found.
            Exception: For other unexpected errors.
        """
        try:
            logger.info(f"Fetching digital assets with IDs: {digital_asset_ids}")
            assets = await self.__digital_asset_repository.get_digital_assets_by_digital_asset_ids(
                digital_asset_ids
            )
            results: List[DigitalAssetResponse] = [
                DigitalAssetResponse(
                    id=asset.id,
                    name=asset.name,
                    partner_id=asset.partner_id,
                    version=asset.version,
                    url=StorageHelper.get_presigned_url(asset.name),
                    asset_type=asset.asset_type,
                    additional_info=asset.additional_info,
                    created_by=asset.created_by,
                    updated_by=asset.updated_by,
                )
                for asset in assets
            ]
            return results

        except Exception as exec:
            logger.error(
                "Unexpected error while fetching digital assets with IDs {}: {}".format(
                    digital_asset_ids, str(exec)
                )
            )
            raise exec
