from contextlib import AbstractAsyncContextManager
from typing import Callable

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from src.components.digital_assets.logger_adapter import LoggerAdapter
from src.components.digital_assets.models import DigitalAssets

logger = LoggerAdapter().get_logger()


class DigitalAssetRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
    ):
        """
        Initialize the DigitalAssetRepository.

        Args:
            session_factory (Callable[..., AbstractAsyncContextManager[AsyncSession]]): A callable session factory for creating database sessions.
            logger: The logger instance for logging repository operations.
        """
        self.__session_factory = session_factory

    async def get_digital_asset_by_partner_id(
        self, partner_id: int, asset_type: str
    ) -> DigitalAssets:
        """
        Fetch a digital asset by its partner ID and type.

        This method retrieves a digital asset from the database based on the provided partner ID and asset type.
        It logs the success or failure of the operation and returns the digital asset if found.

        Args:
            partner_id (int): The ID of the partner associated with the digital asset.
            asset_type (str): The type of the digital asset (e.g., image, video).

        Returns:
            DigitalAssets: The digital asset object, or None if not found.

        Raises:
            Exception: If an unexpected error occurs during the database operation.
        """
        async with self.__session_factory() as session:
            try:
                logger.info(
                    "Fetching digital asset with partner_id: {}, asset_type: {}".format(
                        partner_id, asset_type
                    )
                )
                get_query = (
                    select(DigitalAssets)
                    .where(
                        DigitalAssets.partner_id == partner_id,
                        DigitalAssets.asset_type == asset_type,
                    )
                    .order_by(desc(DigitalAssets.created_at))
                    .limit(1)
                )
                result: AsyncResult = await session.execute(get_query)
                asset = result.scalars().first()

                if asset:
                    logger.info(
                        "Digital asset found for partner_id: {}, asset_type: {}: {}".format(
                            partner_id, asset_type, asset
                        )
                    )
                else:
                    logger.info(
                        "No digital asset found for partner_id: {}, asset_type: {}".format(
                            partner_id, asset_type
                        )
                    )
                return asset
            except Exception as e:
                logger.error(
                    "An unexpected error occurred while fetching digital asset with partner_id: {}, asset_type: {}. Error: {}".format(
                        partner_id, asset_type, str(e)
                    )
                )
                raise e

    async def get_digital_asset_by_id(self, digital_asset_id: int) -> DigitalAssets:
        """
        Fetch a digital asset by its ID.

        Args:
            digital_asset_id (int): The ID of the digital asset to fetch.

        Returns:
            DigitalAssets: The digital asset object if found, otherwise None.

        Raises:
            Exception: For any unexpected database operation errors.
        """
        async with self.__session_factory() as session:
            try:
                logger.info(f"Fetching digital asset with ID: {digital_asset_id}")
                get_query = select(DigitalAssets).where(
                    DigitalAssets.id == digital_asset_id
                )
                result: AsyncResult = await session.execute(get_query)
                asset = result.scalars().first()

                if asset:
                    logger.info(f"Digital asset found: {asset}")
                else:
                    logger.info(f"No digital asset found with ID: {digital_asset_id}")
                return asset
            except Exception as e:
                logger.error(
                    f"An unexpected error occurred while fetching digital asset with ID: {digital_asset_id}. Error: {str(e)}"
                )
                raise e

    async def create_digital_asset(
        self, partner_id: int, asset_type: str, file_name: str, user_id: int
    ) -> DigitalAssets:
        """
        Persist a digital asset record in the database.

        Args:
            partner_id (int): ID of the partner uploading the asset.
            asset_type (str): Type of the asset (e.g., image, video).
            file_name (str): Name of the uploaded file.
            user_id (int): ID of the user uploading the asset.

        Returns:
            DigitalAssets: The persisted digital asset object.

        Raises:
            Exception: For any unexpected database operation errors.
        """
        async with self.__session_factory() as session:
            try:
                logger.info(
                    "Creating digital asset record. Partner ID: {partner_id}, Asset Type: {asset_type}, File Name: {file_name}".format(
                        partner_id=partner_id,
                        asset_type=asset_type,
                        file_name=file_name,
                    )
                )

                fetch_query = (
                    select(DigitalAssets)
                    .where(
                        DigitalAssets.partner_id == partner_id,
                        DigitalAssets.asset_type == asset_type,
                    )
                    .order_by(desc(DigitalAssets.created_at))
                    .limit(1)
                )
                result = await session.execute(fetch_query)
                latest_asset = result.scalars().first()

                new_version = 1
                if latest_asset:
                    new_version = (
                        latest_asset.version + 1 if latest_asset.version < 3 else 1
                    )

                logger.info(
                    "Determined new version for digital asset: {}".format(new_version)
                )

                new_asset = DigitalAssets(
                    name=file_name,
                    partner_id=partner_id,
                    asset_type=asset_type,
                    version=new_version,
                    created_by=user_id,
                    updated_by=user_id,
                )

                session.add(new_asset)
                await session.commit()
                await session.refresh(new_asset)

                logger.info("Digital asset created successfully: {}".format(new_asset))
                return new_asset
            except Exception as e:
                logger.error(
                    "An unexpected error occurred while fetching digital asset with partner_id: {}, asset_type: {}. Error: {}".format(
                        partner_id, asset_type, str(e)
                    )
                )
                raise e

    async def delete_digital_asset_by_id(self, digital_asset_id: int) -> bool:
        """
        Delete a digital asset by its ID from the database.

        Args:
            digital_asset_id (int): The ID of the digital asset to delete.

        Returns:
            bool: True if the asset was deleted, False if not found.

        Raises:
            Exception: For any unexpected database operation errors.
        """
        async with self.__session_factory() as session:
            try:
                logger.info(f"Deleting digital asset with ID: {digital_asset_id}")
                delete_query = delete(DigitalAssets).where(
                    DigitalAssets.id == digital_asset_id
                )
                result = await session.execute(delete_query)
                await session.commit()

                if result.rowcount > 0:
                    logger.info(
                        f"Digital asset with ID: {digital_asset_id} deleted successfully"
                    )
                    return True
                else:
                    logger.info(f"No digital asset found with ID: {digital_asset_id}")
                    return False
            except Exception as e:
                logger.error(
                    f"Error deleting digital asset with ID: {digital_asset_id}. Error: {str(e)}"
                )
                raise e

    async def get_digital_assets_by_digital_asset_ids(
        self, digital_asset_ids: list[int]
    ) -> list[DigitalAssets]:
        try:
            async with self.__session_factory() as session:
                logger.info(
                    "Fetching digital assets with IDs: {}".format(digital_asset_ids)
                )
                query = select(DigitalAssets).where(
                    DigitalAssets.id.in_(digital_asset_ids)
                )
                result: AsyncResult = await session.execute(query)
                assets = result.scalars().all()

                if not assets:
                    logger.info("No digital assets found for the provided IDs")
                    return assets
                logger.info("Digital assets found for the provided IDs")
                return assets
        except Exception as exec:
            logger.error(
                "An unexpected error occurred while fetching digital assets with IDs: {}. Error: {}".format(
                    digital_asset_ids, str(exec)
                )
            )
            raise exec
