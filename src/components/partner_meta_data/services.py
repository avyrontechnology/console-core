from uuid import UUID
import copy
import json
from typing import Iterator, Union

from dependency_injector.wiring import Provide
from fastapi import Depends

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.common.actions import AuditActions
from src.components.common.datetime import DateTimeUtil
from src.components.common.resources import Resource
from src.components.partner.error import PartnerNotFoundError
from src.components.partner_config.services import PartnerConfigService
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.partner_meta_data.repositories import PartnerMetaDataRepository
from src.components.partner_meta_data.schema import (
    PartnerMetadata,
    PartnerMetaDataResponse,
    PartnerPlanDetailsResponse,
    UpdatePartnerMetaData,
)
from src.exceptions import PartnerMetaDataException, PartnerNotFoundException
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerMetaDataServices:

    def __init__(
        self,
        audit_service: AuditService,
        partner_meta_data_repository=PartnerMetaDataRepository,
        console_service_logger=ConsoleServiceLogger,
    ) -> None:
        self.__partner_meta_data_repository: PartnerMetaDataRepository = (
            partner_meta_data_repository
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__audit_service: AuditService = audit_service

    async def is_partner_exists(self, partner_id: UUID) -> bool:
        try:
            return await self.__partner_meta_data_repository.is_partner_exists(
                partner_id
            )
        except Exception as e:
            self.__console_service_logger.error(
                "Error checking if partner exists: {}".format(e)
            )
            raise e

    async def create_partner_metadata(
        self,
        partner_id: UUID,
        partner_meta_data: PartnerMetadata,
    ):
        try:
            self.__console_service_logger.info(
                "Creating partner data for partner id : {}".format(partner_id)
            )
            if not await self.__partner_meta_data_repository.is_partner_exists(
                partner_id
            ):
                raise PartnerNotFoundError(partner_id)

            created_partner_metadata: PartnerMetaData = (
                await self.__partner_meta_data_repository.add_partner_metadata_repository(
                    partner_id=partner_id, partner_meta_data=partner_meta_data
                )
            )

            self.__console_service_logger.info(
                "Partner metadata created successfully, partner id: {}".format(
                    partner_id
                )
            )
            log_entry = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.partner_meta_data,
                resource_id=created_partner_metadata.id,
                resource_previous_state=None,
                resource_current_state=str(partner_meta_data),
                performed_by=partner_id,
                details="Partner meta data created with id: {}".format(
                    created_partner_metadata.id
                ),
            )
            await self.__audit_service.log_action(log_entry)
            return PartnerMetaDataResponse.model_validate(created_partner_metadata)
        except PartnerMetaDataException as exec:
            self.__console_service_logger.error(
                "Integrity error occured while creating partner, error:{}".format(
                    str(exec)
                )
            )
            raise exec
        except Exception as ex:
            self.__console_service_logger.error(
                "an unexpected error occured while creating partner metadata for partner id: {}".format(
                    partner_id
                )
            )
            raise ex

    async def update_partner_meta_data(
        self, partner_id: UUID, update_data: UpdatePartnerMetaData
    ) -> PartnerMetaData:
        try:
            # Checking if partner exists or not
            if not await self.__partner_meta_data_repository.is_partner_exists(
                partner_id
            ):
                raise PartnerNotFoundException

            partner_meta_data: PartnerMetaData | None = (
                await self.__partner_meta_data_repository.get_partner_meta_data_by_partner_id(
                    partner_id
                )
            )

            if not partner_meta_data:
                created_parnter_meta_data: PartnerMetaDataResponse = (
                    await self.create_partner_metadata(partner_id, update_data)
                )
                partner_meta_data: PartnerMetaData = created_parnter_meta_data.__dict__
                return partner_meta_data

            resource_previous_state = copy.deepcopy(partner_meta_data)
            self.__console_service_logger.info(
                "Attempting to update partner metadata for partner_id {}".format(
                    partner_id
                )
            )
            updated_metadata = (
                await self.__partner_meta_data_repository.update_partner_meta_data(
                    partner_id, update_data
                )
            )
            self.__console_service_logger.info(
                "Partner metadata updated successfully, id: {}".format(partner_id)
            )
            resource_previous_state_json = json.dumps(
                resource_previous_state.__dict__, default=str
            )
            resource_current_state_json = json.dumps(
                updated_metadata.__dict__, default=str
            )
            log_entry = AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.partner_meta_data,
                resource_id=updated_metadata.id,
                resource_previous_state=(resource_previous_state_json),
                resource_current_state=(resource_current_state_json),
                performed_by=partner_id,
                details="Partner meta data with id: {} is updated successfully".format(
                    updated_metadata.id
                ),
            )
            await self.__audit_service.log_action(log_entry)
            return updated_metadata
        except PartnerMetaDataException as ex:
            self.__console_service_logger.error(
                "Error occurred while update partner metadata for partner_id {}".format(
                    ex
                )
            )
            raise PartnerMetaDataException(ex)
        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while update partner metadata for partner_id {}".format(
                    ex
                )
            )
            raise

    async def get_all_partner_meta_data(self) -> Iterator[PartnerMetaData]:
        try:
            self.__console_service_logger.info("Attempting to get all partner metadata")
            get_all_metadata = (
                await self.__partner_meta_data_repository.get_all_partner_meta_data()
            )
            self.__console_service_logger.info(
                "Successfully fetched all partner metadata: {}".format(get_all_metadata)
            )

            return get_all_metadata
        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while get all partner metadata for partner {}".format(
                    ex
                )
            )
            raise

    async def get_partner_meta_data_by_partner_id(
        self, partner_id: UUID
    ) -> Union[PartnerMetaData, None]:
        try:
            self.__console_service_logger.info(
                "Attempting to get partner metadata by partner id: {}".format(
                    partner_id
                )
            )
            partner_meta_data = await self.__partner_meta_data_repository.get_partner_meta_data_by_partner_id(
                partner_id
            )
            self.__console_service_logger.info(
                "Successfully fetched partner metadata by partner_id {} {}".format(
                    partner_id, partner_meta_data
                )
            )
            if not partner_meta_data:
                return None

            return PartnerMetaDataResponse.model_validate(partner_meta_data)
        except PartnerMetaDataException as ex:
            self.__console_service_logger.error(
                "Error occurred while get partner metadata by partner_id {}".format(ex)
            )
            raise PartnerMetaDataException(ex)
        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while get partner metadata by partner_id {}".format(ex)
            )
            raise

    async def get_partner_plan_details(
        self,
        partner_id: UUID,
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
    ) -> PartnerPlanDetailsResponse:
        try:
            self.__console_service_logger.info(
                f"Attempting to get partner: {partner_id} plan details."
            )

            meta_data: PartnerMetaData = await self.get_partner_meta_data_by_partner_id(
                partner_id=partner_id
            )

            service_enabled_for_partner = (
                await partner_config_service.get_partner_configs_by_partner_id(
                    partner_id
                )
            )

            if not meta_data:
                self.__console_service_logger.warning(
                    f"Partner meta data not found for partner: {partner_id}"
                )
                return PartnerPlanDetailsResponse()
            if service_enabled_for_partner and isinstance(
                service_enabled_for_partner[0], dict
            ):
                services_enabled_dict = {
                    item["key"]: item["value"] for item in service_enabled_for_partner
                }
            elif service_enabled_for_partner:
                services_enabled_dict = {
                    item.key: item.value for item in service_enabled_for_partner
                }
            else:
                services_enabled_dict = {}

            service_info = PartnerPlanDetailsResponse(
                is_talko_service_enabled=services_enabled_dict.get(
                    "is_talko_enabled", False
                ),
                can_create_deals=services_enabled_dict.get("can_create_deals", False),
                can_add_workflow=services_enabled_dict.get("can_add_workflow", False),
                can_view_workflow=services_enabled_dict.get("can_view_workflow", False),
                is_mailer_enabled=services_enabled_dict.get("is_mailer_enabled", False),
                is_gsm_calling_enabled=services_enabled_dict.get(
                    "is_gsm_calling_enabled", False
                ),
                can_view_task_management=services_enabled_dict.get(
                    "can_view_task_management", False
                ),
                is_meeting_log_enabled=services_enabled_dict.get(
                    "is_meeting_log_enabled", False
                ),
                subscription_mode=services_enabled_dict.get("subscription_mode"),
                is_rule_based_assignment_enabled=services_enabled_dict.get(
                    "is_rule_based_assignment_enabled", False
                ),
                can_view_pipeline_management=services_enabled_dict.get(
                    "can_view_pipeline_management", False
                ),
                can_view_contact=services_enabled_dict.get("can_view_contact", False),
                can_view_organization=services_enabled_dict.get(
                    "can_view_organization", False
                ),
                enable_dialer=services_enabled_dict.get("enable_dialer", False),
                is_bulk_workflow_enabled=services_enabled_dict.get('is_bulk_workflow_enabled', False),
                can_view_mview_management = services_enabled_dict.get('can_view_mview_management', False),
                is_advance_filter_enabled = services_enabled_dict.get('is_advance_filter_enabled', False),
                can_view_template_management=services_enabled_dict.get("can_view_template_management", False),
                can_view_product_management=services_enabled_dict.get("can_view_product_management", False),
                can_add_address_with_google_places=services_enabled_dict.get("can_add_address_with_google_places", False),
                can_view_finance_management=services_enabled_dict.get("can_view_finance_management", False),
                can_view_csf_lead_listing=services_enabled_dict.get("can_view_csf_lead_listing", False),
                is_teams_enabled=bool(services_enabled_dict.get("is_teams_enabled")),
                is_team_data_partition_enabled=bool(services_enabled_dict.get("is_team_data_partition_enabled")),
                can_view_products=services_enabled_dict.get("can_view_products", False),
                can_view_inventory=services_enabled_dict.get("can_view_inventory", False),
                can_view_order_management=services_enabled_dict.get("can_view_order_management", False),
                is_partner_custom_roles_enabled=bool(services_enabled_dict.get("is_partner_custom_roles_enabled")),
                is_user_tracker_enabled=services_enabled_dict.get("is_user_tracker_enabled", False),
                can_view_payment_history=services_enabled_dict.get("can_view_payment_history", False),
                is_reenquiry_chain_enabled=services_enabled_dict.get("is_reenquiry_chain_enabled", False),
                can_view_report_management=services_enabled_dict.get("can_view_report_management", False),
                can_view_helpdesk_management=services_enabled_dict.get("can_view_helpdesk_management", False),
                can_download_call_logs=services_enabled_dict.get("can_download_call_logs", False),
                is_inbox_enabled=services_enabled_dict.get("is_inbox_enabled", False),
                is_field_tracking_enabled=services_enabled_dict.get("is_field_tracking_enabled", False),
                can_view_inactive_agents=services_enabled_dict.get("can_view_inactive_agents", False),
                is_agent_availability_based_assignment_enabled=services_enabled_dict.get("is_agent_availability_based_assignment_enabled", False),
                is_sticky_dids_enabled=services_enabled_dict.get("is_sticky_dids_enabled", False),
                is_assignee_sync_enabled=services_enabled_dict.get("is_assignee_sync_enabled", False),
            )
            if (
                meta_data.talko_trail_expiry_time
                and meta_data.talko_trail_expiry_time > DateTimeUtil.get_current_time()
            ):
                service_info.is_talko_service_free_trial_enabled = True

            return service_info

        except Exception as exc:
            self.__console_service_logger.error(
                f"Unexpected error occurred while getting partner: {partner_id} plan details, error: {exc}"
            )
            raise

    async def get_partner_meta_data_by_partner_ids(
        self, partner_ids: list[int]
    ) -> dict[int, dict]:
        try:
            self.__console_service_logger.info(
                "Attempting to get partner metadata by partner ids: {}".format(
                    partner_ids
                )
            )

            meta_data_list = await self.__partner_meta_data_repository.get_partner_meta_data_by_partner_ids(
                partner_ids
            )

            self.__console_service_logger.info(
                "Successfully fetched partner metadata by partner_ids {} {}".format(
                    partner_ids, meta_data_list
                )
            )

            current_time = DateTimeUtil.get_current_time()

            # Start with default False for all partners
            partner_meta_map = {
                pid: {"meta": None, "is_talko_free_trial_enabled": False}
                for pid in partner_ids
            }

            # Fill real values where metadata exists
            for meta in meta_data_list:
                is_free_trial_enabled = (
                    meta.talko_trail_expiry_time is not None
                    and meta.talko_trail_expiry_time > current_time
                )

                partner_meta_map[meta.partner_id] = {
                    "meta": meta,
                    "is_talko_free_trial_enabled": is_free_trial_enabled,
                }

            return partner_meta_map

        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while get partner metadata by partner_ids {}".format(ex)
            )
            raise
