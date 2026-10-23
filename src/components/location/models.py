import uuid
from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from src.components.database.base_model import MetaData
from src.core.db import Base


class Countries(MetaData):
    __tablename__ = "console_countries"

    name = Column(String(128), unique=True, nullable=False, index=True)
    slug = Column(String(128), unique=True, nullable=False)

    # Relationship to States and Users
    states = relationship("States", back_populates="country")
    users = relationship("User", back_populates="country")

    def __repr__(self):
        return f"<Country(id={self.id}, name={self.name})>"


class States(MetaData):
    __tablename__ = "console_states"

    name = Column(String(128), nullable=False, index=True)
    slug = Column(String(128), unique=True, nullable=False)
    country_id = Column(
        UUID(as_uuid=True), ForeignKey("console_countries.id", ondelete="CASCADE"), index=True
    )

    # Relationship to Countries and Cities and user
    country = relationship("Countries", back_populates="states")
    cities = relationship("Cities", back_populates="state")
    users = relationship("User", back_populates="state")

    def __repr__(self):
        return f"<State(id={self.id}, name={self.name}, country_id={self.country_id})>"


class Cities(MetaData):
    __tablename__ = "console_cities"

    name = Column(String(128), nullable=False, index=True)
    slug = Column(String(128), unique=True, nullable=False)
    state_id = Column(
        UUID(as_uuid=True), ForeignKey("console_states.id", ondelete="CASCADE"), index=True
    )

    # Relationship to States and Users
    state = relationship("States", back_populates="cities")
    users = relationship("User", back_populates="city")

    def __repr__(self):
        return f"<City(id={self.id}, name={self.name}, state_id={self.state_id})>"
