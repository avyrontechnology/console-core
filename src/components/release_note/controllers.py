from uuid import UUID
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, UploadFile, Form, File , Query
from typing import Optional, List

from src.components.release_note import schemas
from src.components.release_note.schemas import (
    ReleaseNotesResponse,
    ReleaseNotesbyidResponse,
    ReleaseNotesbyallResponse,
    ReleaseNoteHistoryResponse,
)
from src.components.release_note.services import ReleaseNotesService
from src.components.release_note.errors import ReleaseNoteNotFoundError
from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    SuccessResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceCreatedResponse,
)
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger

logger = ConsoleServiceLogger.get_logger()


class ReleaseNoteController:

    release_note_router = APIRouter()

    # =========================
    # CREATE RELEASE NOTE
    # =========================
    @release_note_router.post(
        "/upload_release_note",
        response_model=schemas.ReleaseNotesResponse,
        description="Create a new release note",
    )
    @permission_check("console:upload_release_note")
    @inject
    async def upload_release_note(
        request: Request,
        svc_name: str = Form(...),
        title: str = Form(...),
        description: str = Form(...),
        markup: str = Form(...),
        file: UploadFile = File(None),
        release_notes_service: ReleaseNotesService = Depends(
            Provide[Container.release_notes_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            user_id: UUID = current_user.get("user_id")
            partner_id: UUID = current_user.get("partner_id")

            logger.info(
            f"User {user_id} creating release note for svc: {svc_name}"
            )
            
            created_note :ReleaseNotesResponse = await release_notes_service.create_release_note(
                title=title,
                description=description,
                input_file=file,
                user_id=user_id,
                partner_id=partner_id,
                svc_name=svc_name,
                markup=markup,
            )
            
            logger.info(f"Release note created successfully by user {user_id}")


            return ResourceCreatedResponse(data=created_note)

        except Exception as exc:
            logger.error(f"Unexpected error creating release note: {repr(exc)}")
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    # =========================
    # GET RELEASE NOTE BY ID
    # =========================
    @release_note_router.get(
        "/release_note/{release_note_id}",
        response_model=schemas.ReleaseNotesbyidResponse,
        description="Fetch release note by ID",
    )
    @permission_check("console:get_release_note")
    @inject
    async def get_release_note(
        request: Request,
        release_note_id: UUID,
        svc_name: Optional[str] = Query(None),
        release_notes_service: ReleaseNotesService = Depends(
            Provide[Container.release_notes_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            partner_id: UUID = current_user.get("partner_id")

            logger.info(f"Fetching release note id {release_note_id} for svc: {svc_name}")
            
            data: ReleaseNotesbyidResponse = await release_notes_service.get_release_note_by_id(
                    release_note_id=release_note_id,
                    partner_id=partner_id,
                    current_user=current_user, 
                    svc_name=svc_name               
            )
            return SuccessResponse(data=data)

        except ReleaseNoteNotFoundError as exc:
            logger.error(f"Release note not found: {repr(exc)}")
            return NotFoundResponse(str(exc))

        except Exception as exc:
            logger.error(f"Unexpected error fetching release note: {repr(exc)}")
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
    
    
    # =========================
    # GET All RELEASE NOTE
    # =========================
    @release_note_router.get(
    "/release_notes",
    response_model=List[schemas.ReleaseNotesbyallResponse], 
    description="Fetch all release notes",
    )
    @permission_check("console:get_all_release_notes")
    @inject
    async def get_all_release_notes(
        request: Request,
        release_notes_service: ReleaseNotesService = Depends(
            Provide[Container.release_notes_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            partner_id: UUID = current_user.get("partner_id")

            logger.info(
                "API call: Fetching all release notes for partner_id=%s",
                partner_id,
            )

            data: list[ReleaseNotesbyallResponse]  = await release_notes_service.get_all_release_notes(
                partner_id=partner_id,
                current_user=current_user
            )

            return SuccessResponse(data=data)
        
        except ReleaseNoteNotFoundError as exc:
            logger.error(f"Release note not found: {repr(exc)}")
            return NotFoundResponse(str(exc))

        except Exception as exc:
            logger.error(f"Unexpected error updating release note: {repr(exc)}")
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
        
        
    # =========================
    # UPDATE RELEASE NOTE
    # =========================
    @release_note_router.put(
        "/release_note/{release_note_id}",
        response_model=schemas.ReleaseNotesResponse,
        description="Update release note by ID",
    )
    @permission_check("console:update_release_note")
    @inject
    async def update_release_note(
        request: Request,
        release_note_id: UUID,
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        file: UploadFile = File(None),
        markup: Optional[str] = Form(None) ,
        release_notes_service: ReleaseNotesService = Depends(
            Provide[Container.release_notes_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            user_id: UUID = current_user.get("user_id")
            partner_id: UUID = current_user.get("partner_id")

            logger.info(f"Updating release note id {release_note_id}")

            updated_note : ReleaseNotesResponse = await release_notes_service.update_release_note(
                release_note_id=release_note_id,
                title=title,
                description=description,
                input_file=file,
                user_id=user_id,
                partner_id=partner_id,
                current_user=current_user,
                markup=markup,  
            )

            return SuccessResponse(data=updated_note)

        except ReleaseNoteNotFoundError as exc:
            logger.error(f"Release note not found: {repr(exc)}")
            return NotFoundResponse(str(exc))

        except Exception as exc:
            logger.error(f"Unexpected error updating release note: {repr(exc)}")
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
        
    # =========================
    # GET RELEASE NOTE HISTORY
    # =========================
    @release_note_router.get(
        "/release_note/{release_note_id}/history",
        response_model=schemas.ReleaseNoteHistoryResponse,
        description="Fetch release note history by ID",
    )
    @permission_check("console:get_release_note_history")
    @inject
    async def get_release_note_history(
        request: Request,
        release_note_id: UUID,
        release_notes_service: ReleaseNotesService = Depends(
            Provide[Container.release_notes_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            partner_id: UUID = current_user.get("partner_id")

            logger.info(f"Fetching release note history for id {release_note_id}")

            history: ReleaseNoteHistoryResponse = await release_notes_service.get_release_note_history(
                release_note_id=release_note_id,
                partner_id=partner_id,
                current_user=current_user
            )

            return SuccessResponse(data=history)

        except ReleaseNoteNotFoundError as exc:
            logger.error(f"Release note not found: {repr(exc)}")
            return NotFoundResponse(str(exc))

        except Exception as exc:
            logger.error(f"Unexpected error fetching history: {repr(exc)}")
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)