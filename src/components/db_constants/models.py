import uuid
from sqlalchemy import JSON, Column, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import force_auto_coercion

from src.components.database.base_model import MetaData

force_auto_coercion()


class ConstantsBase(MetaData):
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    name = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=0)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
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

    value = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<GlobalMediaConstants(id={self.id}, name={self.name}, value={self.value})>"


class Constants(ConstantsBase):
    __tablename__ = "constants"


class DynamicVariables(ConstantsBase):
    __tablename__ = "dynamic_variables"


class MediaConstants(ConstantsBase):
    __tablename__ = "media_constants"

    value = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<MediaConstants(id={self.id}, name={self.name}, value={self.value})>"
