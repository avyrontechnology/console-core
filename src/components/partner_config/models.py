from copy import deepcopy

import uuid
from sqlalchemy import Boolean, Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from src.components.common.datetime import DateTimeUtil
from src.components.database.base_model import MetaData


class PartnerConfig(MetaData):
    __tablename__ = "console_partner_config"

    partner_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    key = Column(String(255), nullable=False, index=True)
    value = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    history = Column(JSON, default=list)

    __table_args__ = (UniqueConstraint("partner_id", "key", name="_partner_key_uc"),)

    def update_history(self, old_value, new_value):
        """Updates the history field with the last five changes."""
        if not isinstance(self.history, list):
            self.history = []  # Ensure it's a list

        entry = {
            "version": len(self.history) + 1,
            "previous_value": old_value,
            "updated_value": new_value,
            "updated_at": DateTimeUtil.get_current_time(),
        }
        new_history = deepcopy(self.history)
        new_history.append(entry)

        if len(self.history) > 5:
            self.history.pop(0)
        self.history = new_history
