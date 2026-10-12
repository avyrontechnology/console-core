from uuid import UUID
from typing import Optional , List , Dict, Any
from fastapi import UploadFile , File

from src.components.release_note.errors import ReleaseNoteUpdateError
from src.components.release_note.models import ReleaseNotes
from src.components.release_note.repositories import ReleaseNotesRepository
from src.components.release_note.schemas import (
    ReleaseNotesResponse,
    ReleaseNotesbyidResponse,
    ReleaseNotesbyallResponse,
)
from src.components.common.constants import CurrentUserMap

from src.loggers.console_service_logger import ConsoleServiceLogger

from src.components.release_note.errors import (
    ReleaseNoteNotFoundError,
    UnauthorizedReleaseNoteAccessError,
    ReleaseNoteFileUploadError,
)
logger = ConsoleServiceLogger.get_logger()

class ReleaseNotesService:

    def __init__(
        self,
        release_notes_repository: ReleaseNotesRepository,
    ):
        self.__release_notes_repository = release_notes_repository
        
    # ======================================================
    # COMMON HELPERS (NEW - SAFE)
    # ======================================================

    async def _get_note_or_raise(self, release_note_id: UUID) -> ReleaseNotes:
        note = await self.__release_notes_repository.get_release_note_by_id(release_note_id)
        if not note:
            raise ReleaseNoteNotFoundError(release_note_id)
        return note

    def _check_access(self, note: ReleaseNotes, partner_id: UUID, current_user: dict):
        current_user_hierarchy = current_user.get(CurrentUserMap.ROLE_HIERARCHY_LEVEL)

        if (
            note.partner_id != partner_id
            and current_user_hierarchy > CurrentUserMap.SUPER_ADMIN_ROLE_HIERARCHY_LEVEL
        ):
            raise UnauthorizedReleaseNoteAccessError()

    async def _upload_file(
        self,
        input_file: File,
        partner_id: UUID,
        user_id: UUID,
    ) -> Optional[str]:
        # File storage retired: refuse files, keep
        # text-only notes working.
        if not input_file or not input_file.filename:
            return None
        raise ReleaseNoteFileUploadError()

    def _build_file_url(self, file_path: Optional[str]) -> Optional[str]:
        return None

    def _attach_urls_to_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return history


    # ======================================================
    # CREATE RELEASE NOTE
    # ======================================================
    async def create_release_note(
        self,
        title: str,
        description: str,
        markup: str,
        input_file: File,
        user_id: UUID,
        partner_id: UUID,
        svc_name: str, 
    ) -> ReleaseNotesResponse:

        try:
            logger.info(
                f"Creating release note for user_id: {user_id} and svc: {svc_name}"
            )

            da_file_path: Optional[str] = await self._upload_file(input_file, partner_id, user_id)


            release_note: ReleaseNotes = (
                await self.__release_notes_repository.create_release_note(
                    title=title,
                    description=description,
                    markup=markup,   
                    da_file_path=da_file_path,
                    partner_id=partner_id,
                    user_id=user_id,
                    svc_name=svc_name
                )
            )

            file_url: Optional[str] = None
             # FULL VERSION HISTORY
            history: List[Dict[str, Any]]  = release_note.version_history or []

            history = self._attach_urls_to_history(history)
            
            return ReleaseNotesResponse(
                id=release_note.id,
                title=release_note.title,
                description=release_note.description,
                file_path=release_note.da_file_path,
                version_history=history, 
                file_url=file_url,
                created_at=release_note.created_at,
                updated_at=release_note.updated_at,
                svc_name=release_note.svc_name ,
                markup=release_note.markup 
            )

        except Exception as exc:
            logger.error(
                "Error while creating release note: {}".format(str(exc))
            )
            raise exc

    # ======================================================
    # GET RELEASE NOTE BY ID
    # ======================================================
    async def get_release_note_by_id(
        self,
        release_note_id: UUID,
        partner_id: UUID,
        current_user:dict,
        svc_name: Optional[str],  
        
    ) -> ReleaseNotesbyidResponse:

        try:
            logger.info(
                f"Fetching release note with id: {release_note_id} for svc: {svc_name}"
            )
            
            current_user_hierarchy=current_user.get(CurrentUserMap.ROLE_HIERARCHY_LEVEL)

            release_note :ReleaseNotes = await self.__release_notes_repository.get_release_note_by_id(
                release_note_id,
                svc_name=None
            )

            if not release_note:
                raise ReleaseNoteNotFoundError(release_note_id)

            if (
                release_note.partner_id != partner_id 
                and current_user_hierarchy
                > CurrentUserMap.SUPER_ADMIN_ROLE_HIERARCHY_LEVEL
            ):
                logger.warning(
                    "Unauthorized access attempt for release_note_id=%s with partner_id=%s and svc=%s",
                    release_note.id,
                    partner_id,
                    svc_name,
                )
                raise UnauthorizedReleaseNoteAccessError()
            
            file_url = self._build_file_url(release_note.da_file_path)

            history: List[Dict[str, Any]]  = release_note.version_history or []

            history = self._attach_urls_to_history(history)

            return ReleaseNotesbyidResponse(
                id=release_note.id,
                title=release_note.title,
                description=release_note.description,
                file_path=release_note.da_file_path,
                file_url=file_url,
                version_history=history,
                created_at=release_note.created_at,
                created_by=release_note.created_by,
                updated_by=release_note.updated_by,
                svc_name=release_note.svc_name ,
                markup=release_note.markup 
            )

        except ReleaseNoteNotFoundError as exc:
            logger.error(
                "Release note not found: {}".format(str(exc))
            )
            raise exc

        except Exception as exc:
            logger.error(
                "Error while fetching release note: {}".format(str(exc))
            )
            raise exc
    
    # ======================================================
    # GET ALL RELEASE NOTE 
    # ======================================================
    
    async def get_all_release_notes(
        self,
        partner_id: UUID,
        current_user: dict,
    ) -> list[ReleaseNotesbyallResponse]:

        try:
            logger.info(
                "Fetching all release notes for partner_id: {}".format(partner_id)
            )
            
            current_user_hierarchy = current_user.get(
              CurrentUserMap.ROLE_HIERARCHY_LEVEL
            )
            
            release_notes :List[ReleaseNotes] = await self.__release_notes_repository.get_all_release_notes(
                partner_id
            )
            
            response = []
            
            for release_note in release_notes:

                if (
                release_note.partner_id != partner_id
                and current_user_hierarchy
                > CurrentUserMap.SUPER_ADMIN_ROLE_HIERARCHY_LEVEL
            ):
                 continue
            
                file_url: Optional[str] = None
                version = None
                if release_note.version_history and len(release_note.version_history) > 0:
                    version = release_note.version_history[-1].get("version")


                response.append(
                    ReleaseNotesbyallResponse(
                        id=release_note.id,
                        title=release_note.title,
                        version=version,
                        description=release_note.description,
                        file_path=release_note.da_file_path,
                        file_url=file_url,
                        created_at=release_note.created_at,
                        updated_at=release_note.updated_at,
                        markup=release_note.markup,
                    )
                )

            return response

        except Exception as exc:
            logger.error(
                "Error while fetching all release notes: {}".format(str(exc))
            )
            raise exc

    # ======================================================
    # UPDATE RELEASE NOTE
    # ======================================================
    async def update_release_note(
        self,
        release_note_id: UUID,
        title: Optional[str],
        description: Optional[str],
        markup: Optional[str],
        input_file: Optional[UploadFile],
        user_id: UUID,
        partner_id: UUID,
        current_user: dict,
    ) -> ReleaseNotesResponse:

        try:
            logger.info(f"Updating release note with id: {release_note_id}")
            
            existing_note: ReleaseNotes = await self._get_note_or_raise(release_note_id)

            self._check_access(existing_note, partner_id, current_user)

            uploaded_path: Optional[str] = None
            
            if input_file is not None:
                uploaded_path = await self._upload_file(input_file, partner_id, user_id)            
           
            new_file_path: Optional[str] = uploaded_path or existing_note.da_file_path 
                       
            new_title = title if title is not None else existing_note.title
            new_description = description if description is not None else existing_note.description
            new_markup = markup if markup is not None else existing_note.markup   

            
            existing_note.update_version_history(
            title=new_title,
            description=new_description,
            file_path=new_file_path,
            markup=new_markup,
            user_id=user_id,
        )

            
            updated_note: Optional[ReleaseNotes] = await self.__release_notes_repository.update_release_note(
                release_note_id=release_note_id,
                title=new_title,
                description=new_description,
                markup=new_markup,  
                da_file_path=new_file_path,
                user_id=user_id,
                version_history=existing_note.version_history,
            )
            
            if not updated_note:
               raise ReleaseNoteUpdateError()
                    
            file_url: Optional[str] = self._build_file_url(updated_note.da_file_path)

            history: List[Dict[str, Any]] = (updated_note.version_history or [])[::-1]
            
            history = self._attach_urls_to_history(history)


            return ReleaseNotesResponse(
                id=updated_note.id,
                title=updated_note.title,
                description=updated_note.description,
                version_history=history,
                file_path=updated_note.da_file_path,
                file_url=file_url,
                created_at=updated_note.created_at,
                updated_at=updated_note.updated_at,
                svc_name=existing_note.svc_name,
                markup=updated_note.markup,  
            )

        except ReleaseNoteNotFoundError as exc:
            logger.error(
                "Release note not found: {}".format(str(exc))
            )
            raise exc

        except Exception as exc:
            logger.error(
                "Error while updating release note: {}".format(str(exc))
            )
            raise exc
        
    # ======================================================
    # GET RELEASE NOTE HISTORY
    # ======================================================
    async def get_release_note_history(
        self,
        release_note_id: UUID,
        partner_id: UUID,
        current_user: dict,
    ) -> List[Dict[str, Any]]:

        try:
            logger.info(f"Fetching history for release note id: {release_note_id}")

            release_note :Optional[ReleaseNotes] = await self.__release_notes_repository.get_release_note_by_id(
                release_note_id
            )

            if not release_note:
                raise ReleaseNoteNotFoundError(release_note_id)
            
            current_user_hierarchy = current_user.get(
                CurrentUserMap.ROLE_HIERARCHY_LEVEL
            )

            if (
                release_note.partner_id != partner_id
                and current_user_hierarchy
                > CurrentUserMap.SUPER_ADMIN_ROLE_HIERARCHY_LEVEL
            ):
                logger.warning(
                    f"Unauthorized history access for release_note_id={release_note.id}"
                )
                raise UnauthorizedReleaseNoteAccessError()
            
            history: List[Dict[str, Any]] = (release_note.version_history or [])[::-1]
            
            history = self._attach_urls_to_history(history)

            
            return history

        except ReleaseNoteNotFoundError as exc:
            logger.error(f"Release note not found: {repr(exc)}")
            raise exc

        except Exception as exc:
            logger.error(f"Error while fetching release note history: {repr(exc)}")
            raise exc

            
           
          
    