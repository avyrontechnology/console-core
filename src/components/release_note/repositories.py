from contextlib import AbstractAsyncContextManager
from typing import Callable, Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession

from src.components.release_note.models import ReleaseNotes
from src.components.digital_assets.logger_adapter import LoggerAdapter

logger = LoggerAdapter().get_logger()

class ReleaseNotesRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
    ):
        self.__session_factory = session_factory

    # ========================================
    # CREATE RELEASE NOTE
    # ========================================
    async def create_release_note(
        self,
        title: str,
        description: str,
        markup: str,
        da_file_path: Optional[str],
        partner_id: int,
        user_id: int,
        svc_name: str, 
    ) -> ReleaseNotes:

        async with self.__session_factory() as session:
            try:
                logger.info(
                    "Creating release note with title=%s for partner_id=%s by user_id=%s and svc=%s",
                    title,
                    partner_id,
                    user_id,
                    svc_name,
                )

                new_release_note = ReleaseNotes(
                    title=title,
                    description=description,
                    markup=markup,
                    da_file_path=da_file_path,
                    partner_id=partner_id,
                    created_by=user_id,
                    svc_name=svc_name, 
                )

                session.add(new_release_note)
                await session.commit()
                await session.refresh(new_release_note)

                logger.info(
                    f"Release note created successfully: {new_release_note.id}"
                )

                return new_release_note

            except Exception as exc:
                logger.error(
                    f"Error while creating release note. Error: {str(exc)}"
                )
                raise exc

    # ========================================
    # GET RELEASE NOTE BY ID
    # ========================================
    async def get_release_note_by_id(
        self,
        release_note_id: int,
        svc_name: Optional[str]=None, 
    ) -> Optional[ReleaseNotes]:

        async with self.__session_factory() as session:
            try:
                logger.info(
                    f"Fetching release note with id: {release_note_id} for svc: {svc_name}"
                )

                query = select(ReleaseNotes).where(
                    ReleaseNotes.id == release_note_id,
                    
                )
                if svc_name is not None:
                    query = query.where(
                        ReleaseNotes.svc_name == svc_name
                    )

                result: AsyncResult = await session.execute(query)
                release_note = result.scalars().first()

                return release_note

            except Exception as exc:
                logger.error(
                    f"Error while fetching release note id: {release_note_id}. Error: {str(exc)}"
                )
                raise exc
    
    # ========================================
    # GET ALL RELEASE NOTES
    # ========================================
    async def get_all_release_notes(
        self,
        partner_id: int,
    ) -> List[ReleaseNotes]:

        async with self.__session_factory() as session:
            try:
                logger.info(
                    f"Fetching all release notes for partner_id: {partner_id}"
                )

                query = select(ReleaseNotes).where(
                    ReleaseNotes.partner_id == partner_id
                )

                result: AsyncResult = await session.execute(query)
                release_notes = result.scalars().all()

                return release_notes

            except Exception as exc:
                logger.error(
                    f"Error while fetching all release notes for partner_id: {partner_id}. Error: {str(exc)}"
                )
                raise exc
    
    # ========================================
    # UPDATE RELEASE NOTE
    # ========================================
    async def update_release_note(
        self,
        release_note_id: int,
        title: str,
        description: str,
        markup: Optional[str], 
        da_file_path: Optional[str],
        user_id: int,
        version_history: list,
    ) -> Optional[ReleaseNotes]:

        async with self.__session_factory() as session:
            try:
                logger.info(f"Updating release note id: {release_note_id}")

                # Fetch existing record
                query = select(ReleaseNotes).where(
                    ReleaseNotes.id == release_note_id
                )

                result: AsyncResult = await session.execute(query)
                release_note = result.scalars().first()

                if not release_note:
                    return None

                release_note.title = title
                release_note.description = description
                release_note.markup = markup
                release_note.da_file_path = da_file_path
                release_note.updated_by = user_id
               
                
                release_note.version_history = version_history

                # Save changes
                try:
                    await session.commit()
                except:
                    await session.rollback()
                    raise
                await session.refresh(release_note)

                logger.info(
                    f"Release note {release_note.id} updated successfully by user {user_id}"
                )
                return release_note

            except Exception as exc:
                logger.error(
                    f"Error while updating release note id: {release_note_id}. Error: {exc}"
                )
                raise exc
    
    # ================================
    # GET RELEASE NOTE HISTORY 
    # ================================
    async def get_release_note_history(
        self,
        release_note_id: int,
    ) -> Optional[List[dict]]:

        async with self.__session_factory() as session:
            try:
                logger.info(
                    f"Fetching release note history for id: {release_note_id}"
                )

                query = select(ReleaseNotes).where(
                    ReleaseNotes.id == release_note_id
                )

                result: AsyncResult = await session.execute(query)
                release_note = result.scalars().first()

                if not release_note:
                    return None

                return release_note.version_history or []

            except Exception as exc:
                logger.error(
                    f"Error while fetching history for release note id: {release_note_id}. Error: {str(exc)}"
                )
                raise exc