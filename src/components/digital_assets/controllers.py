from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from src.components.digital_assets import schema
from src.components.digital_assets.logger_adapter import LoggerAdapter
from src.components.digital_assets.services import DigitalAssetService
from src.core.container import Container

logger = LoggerAdapter().get_logger()


class DigitalAssetController:
    digital_asset_router = APIRouter()

    @digital_asset_router.get(
        "/digital_assets",
        response_model=schema.DigitalAssetResponse,
        description="Fetch a digital asset by its ID and type",
    )
    @inject
    async def get_digital_assets(
        partner_id: int,
        asset_type: str,
        digital_asset_service: DigitalAssetService = Depends(
            Provide[Container.digital_asset_service]
        ),
    ):
        """
        Fetch the details of a digital asset by its partner ID and type.

        This endpoint retrieves detailed information about a digital asset using the provided
        partner ID and asset type. It returns a response with the asset's metadata, including:
        - name
        - Partner ID
        - Version
        - Asset type
        - Additional information
        - Created by and updated by details

        Args:
            partner_id (int): The partner ID associated with the digital asset.
            asset_type (str): The type of the digital asset (e.g., image, video).

        Returns:
            DigitalAssetResponse: A response model containing the details of the digital asset.

        Raises:
            HTTPException: If an error occurs during the retrieval of asset details, a 500
                           internal server error will be raised with the exception details.
        """
        try:
            logger.info(
                "Fetching digital asset details for partner_id: {}, asset_type: {}".format(
                    partner_id, asset_type
                )
            )
            asset_details = await digital_asset_service.get_digital_asset_details(
                partner_id,
                asset_type,
            )
            logger.info(
                "Successfully fetched digital asset details for partner_id: {}, asset_type: {}".format(
                    partner_id, asset_type
                )
            )
            return asset_details
        except HTTPException as he:
            logger.error(
                "Error occured while featching digital assets for partner_id: {}, asset_type: {}. Error: {}".format(
                    partner_id, asset_type, str(he)
                )
            )
            raise he

        except Exception as e:
            logger.error(
                "Error fetching digital asset details for partner_id: {}, asset_type: {}. Error: {}".format(
                    partner_id, asset_type, str(e)
                )
            )
            raise HTTPException(status_code=500, detail=str(e))

    @digital_asset_router.post(
        "/upload_digital_asset",
        response_model=schema.UploadDigitalAssetResponse,
    )
    @inject
    async def upload_digital_asset(
        request: Request,
        partner_id: int,
        asset_type: str,
        input_file: UploadFile,
        digital_asset_service: DigitalAssetService = Depends(
            Provide[Container.digital_asset_service]
        ),
    ):
        """
        Upload a digital asset to the cloud storage.

        Args:
            request (Request): The HTTP request object containing user state.
            partner_id (int): The ID of the partner uploading the asset.
            asset_type (str): The type of the asset (e.g., image, video).
            input_file (UploadFile): The file to be uploaded.

        Returns:
            DigitalAssetResponse: Contains the file name and URL of the uploaded asset.

        Raises:
            HTTPException: Raised for client-side or server-side errors with appropriate messages.
        """
        try:
            current_user: dict = request.state.user
            user_id: int = current_user.get("user_id")
            logger.info(
                "Received request to upload digital asset. Partner ID: {partner_id}, Asset Type: {asset_type}, User ID: {user_id}".format(
                    partner_id=partner_id, asset_type=asset_type, user_id=user_id
                )
            )
            asset_details = await digital_asset_service.create_digital_asset(
                partner_id,
                asset_type,
                input_file,
                user_id,
            )
            return asset_details
        except HTTPException as he:
            logger.error(
                "Error occured while uploading digital assets. Partner ID: {partner_id}, Asset Type: {asset_type}, Error: {error}".format(
                    partner_id=partner_id, asset_type=asset_type, error=str(he)
                )
            )
            raise he
        except Exception as e:
            logger.exception(
                "Unexpected error occurred during asset upload. Partner ID: {partner_id}, Asset Type: {asset_type}, Error: {error}".format(
                    partner_id=partner_id, asset_type=asset_type, error=str(e)
                )
            )
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred: {}".format(str(e)),
            )

    @digital_asset_router.delete(
        "/delete_digital_asset",
    )
    @inject
    async def delete_digital_asset(
        request: Request,
        asset_id: int,
        digital_asset_service: DigitalAssetService = Depends(
            Provide[Container.digital_asset_service],
        ),
    ):
        """
        Delete a digital asset from the cloud storage.

        Args:
            request (Request): The HTTP request object containing user state.
            asset_id (int): The ID of the digital asset to be deleted.

        Returns:
            dict: A message indicating successful deletion of the digital asset.

        Raises:
            HTTPException: Raised for client-side or server-side errors with appropriate messages.
        """
        logger.info("Received request to delete digital asset with id: {}".format(id))
        try:
            current_user: dict = request.state.user
            user_id: int = current_user.get("user_id")
            logger.info(
                "User ID: {} is attempting to delete digital asset id: {}".format(
                    user_id, asset_id
                )
            )
            await digital_asset_service.delete_digital_asset_by_id(asset_id)
            logger.info(
                "Successfully deleted digital asset with id: {}".format(asset_id)
            )
            return {"message": "Digital asset deleted successfully"}
        except HTTPException as he:
            logger.error(
                "Error occurred while deleting digital asset with id: {}. Error: {}".format(
                    asset_id, str(he)
                )
            )
            raise he
        except Exception as e:
            logger.exception(
                "Unexpected error occurred during asset deletion with id: {}. Error: {}".format(
                    asset_id, str(e)
                )
            )
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred: {}".format(str(e)),
            )
