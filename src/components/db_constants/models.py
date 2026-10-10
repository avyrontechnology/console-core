from sqlalchemy import JSON, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy_utils import force_auto_coercion

from src.components.database.base_model import MetaData
from src.components.digital_assets.models import DigitalAssets

force_auto_coercion()


class ConstantsBase(MetaData):
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    additional_info = Column(JSON, nullable=True)

    def __str__(self):
        return f"{self.__class__.__name__}: id:{self.id}, name:{self.name}, version:{self.version}"

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id}, name={self.name}, value={self.value})>"


class GlobalConstants(ConstantsBase):
    __tablename__ = "global_constants"


class GlobalDynamicVariables(ConstantsBase):
    __tablename__ = "global_dynamic_variables"


class GlobalMediaConstants(ConstantsBase):
    __tablename__ = "global_media_constants"

    value = Column(
        Integer, ForeignKey("digital_assets.id", ondelete="SET NULL"), nullable=True
    )
    media = relationship("DigitalAssets", foreign_keys=[value], uselist=False)

    def __repr__(self):
        return f"<GlobalMediaConstants(id={self.id}, name={self.name}, value={self.value})>"


class Constants(ConstantsBase):
    __tablename__ = "constants"


class DynamicVariables(ConstantsBase):
    __tablename__ = "dynamic_variables"


class MediaConstants(ConstantsBase):
    __tablename__ = "media_constants"

    value = Column(
        Integer, ForeignKey("digital_assets.id", ondelete="SET NULL"), nullable=True
    )
    media = relationship("DigitalAssets", foreign_keys=[value], uselist=False)

    def __repr__(self):
        return f"<MediaConstants(id={self.id}, name={self.name}, value={self.value})>"
