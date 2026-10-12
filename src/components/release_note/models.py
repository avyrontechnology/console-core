import uuid
from uuid import UUID
from sqlalchemy import Column, String, JSON, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from typing import Optional
import time
from src.components.database.base_model import MetaData


class ReleaseNotes(MetaData):
    __tablename__ = "console_release_notes"


    title = Column(String(255), nullable=False)
    partner_id = Column(UUID(as_uuid=True), nullable=False)
    da_file_path = Column(String(255), nullable=True)
    version_history = Column(JSON, nullable=True, default=list)    
    is_active = Column(Boolean, default=True, nullable=False)
    svc_name = Column(String(50), nullable=True)
    markup = Column(Text, nullable=True)  
    
    # ========================================
    # VERSION HISTORY LOGIC 
    # ========================================
    def update_version_history(
        self,
        title: str,
        description: str,
        file_path: str,
        markup: Optional[str],
        user_id: UUID,
    ) -> None:
        """
        Maintain last 5 versions only
        """

        if not isinstance(self.version_history, list):
            self.version_history = []

        history = self.version_history
        
         # ADD CREATE DATA AS v1 (FIRST TIME ONLY)
        if not history:
            history.append({
                "version": "v1",
                "title": self.title,
                "description": self.description,
                "file_path": self.da_file_path,
                "file_url": None,
                "updated_at": self.created_at,
                "markup": self.markup,
                "updated_by": self.created_by,
            })

        # GET LAST VERSION NUMBER
        last_version = int(history[-1]["version"].replace("v", ""))
        new_version = f"v{last_version + 1}"
        

        entry = {
            "version": new_version,
            "title": title,
            "description": description,
            "file_path": file_path,
            "file_url": None,
            "updated_at": int(time.time() * 1000),
            "markup": markup,  
            "updated_by": user_id,
        }

        history.append(entry)

        # KEEP ONLY LAST 5
        if len(history) > 5:
            history = history[-5:]

        self.version_history = history

 