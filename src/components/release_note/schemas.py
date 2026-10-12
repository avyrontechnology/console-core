from uuid import UUID
from pydantic import BaseModel 
from typing import Optional , List , Dict ,Any , Union
    
    
class ReleaseNotesResponse(BaseModel):
    id: UUID
    title: str
    version_history:List[Dict[str, Any]] 
    description: Optional[str]=None
    file_path: Optional[str]=None
    file_url: Optional[str]=None
    created_at: int
    updated_at: Optional[int]=None
    svc_name: str 
    markup: str
    
    class Config:
        from_attributes = True
        
class ReleaseNotesbyidResponse(BaseModel):
    id: UUID
    title: str
    version_history: List[Dict[str, Any]]
    description: Optional[str]=None
    file_path: Optional[str]=None
    file_url: Optional[str]=None
    created_by: UUID
    created_at: int
    updated_by: Optional[UUID]=None
    svc_name: Optional[str] = None
    markup: Optional[str] = None   
    
    class Config:
        from_attributes = True
        
class ReleaseNoteHistoryItem(BaseModel):
    version: str | int
    title: str
    description: Optional[str]=None
    file_path: Optional[str] = None
    file_url: Optional[str] = None
    created_by: UUID
    created_at: int
    markup: Optional[str] = None 

    class Config:
        from_attributes = True


class ReleaseNoteHistoryResponse(BaseModel):
    status: str
    message: str
    data: List[ReleaseNoteHistoryItem]
    
class ReleaseNotesbyallResponse(BaseModel):
    id: UUID
    title: str
    version: Optional[Union[str, int]] = None 
    description: Optional[str] = None
    file_path: Optional[str] = None
    file_url: Optional[str] = None
    created_at: int
    updated_at: Optional[int] = None
    markup: Optional[str] = None

    class Config:
        from_attributes = True