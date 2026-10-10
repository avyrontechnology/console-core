import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Column, Enum, Integer, String
from src.components.digital_assets.constants import DigitalAssetEnum
from src.core.db import Base


class DigitalAssets(Base):
    """
    Represents a digital asset in the database.

    Attributes:
        unique_id (str): A unique identifier (UUID) for the digital asset.
        partner_id (int): The ID of the partner associated with the asset.
        version (int): The version number of the digital asset.
        asset_type (DigitalAssetEnum): The type of the asset, determined by the `DigitalAssetEnum` enum.
        additional_info (dict, optional): Metadata or additional properties associated with the asset.
        created_by (int, optional): The ID of the user who created the asset.
        updated_by (int, optional): The ID of the user who last updated the asset.
        created_at (int): The timestamp (in milliseconds) when the asset was created, defaulting to the current UTC time.
        updated_at (int): The timestamp (in milliseconds) when the asset was last updated, automatically updated on modification.

    Methods:
        __repr__: Returns a string representation of the DigitalAsset instance, including key attributes like `unique_id`, `asset_type`, and `version`.
    """

    __tablename__ = "digital_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(
        String(200), default=lambda: str(uuid.uuid4()), nullable=False, unique=True
    )
    partner_id = Column(Integer, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    asset_type = Column(
        Enum(DigitalAssetEnum, values_callable=lambda x: [e.name for e in x]),
        nullable=False,
    )
    additional_info = Column(JSON, nullable=True)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(
        BigInteger,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        nullable=False,
    )
    updated_at = Column(
        BigInteger,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        onupdate=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        nullable=False,
    )

    def __repr__(self):
        return f"DigitalAsset(name={self.name}, asset_type={self.asset_type}, version={self.version})"
