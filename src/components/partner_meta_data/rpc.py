from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException

from src.components.partner_meta_data.schema import PartnerPlanDetailsResponse
from src.components.common.rpc_uuid import parse_uuid
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.core.container import Container
from src.pub.auth_pb2 import GetPartnerServiceDetailsResponse
from src.pub.auth_pb2_grpc import PartnerMetaDataService


class PartnerMetaDataServiceGrpc(PartnerMetaDataService):

    def __init__(self, logger) -> None:
        self.__logger = logger

    @inject
    async def GetPartnerServicesDetails(
        self,
        request,
        context,
        partner_meta_data_service: PartnerMetaDataServices = Depends(
            Provide[Container.partner_meta_data_service]
        ),
    ):

        partner_id = parse_uuid(request.partner_id, "partner_id")

        self.__logger.info(
            f"Attempting to get partner enabled services details for partner: {partner_id}"
        )

        try:
            plan_details: PartnerPlanDetailsResponse = (
                await partner_meta_data_service.get_partner_plan_details(partner_id)
            )           
            response = GetPartnerServiceDetailsResponse(
                is_talko_service_enabled=plan_details.is_talko_service_enabled,
                is_talko_service_free_trial_enabled=plan_details.is_talko_service_free_trial_enabled,
                can_create_deals=plan_details.can_create_deals,
                can_add_workflow=plan_details.can_add_workflow,
                can_view_workflow=plan_details.can_view_workflow,
                is_mailer_enabled=plan_details.is_mailer_enabled,
                is_gsm_calling_enabled=plan_details.is_gsm_calling_enabled,
                can_view_task_management=plan_details.can_view_task_management,
                is_meeting_log_enabled=plan_details.is_meeting_log_enabled,
                subscription_mode=plan_details.subscription_mode,
                is_rule_based_assignment_enabled=plan_details.is_rule_based_assignment_enabled,
                can_view_pipeline_management = plan_details.can_view_pipeline_management,
                can_view_contact=plan_details.can_view_contact,
                can_view_organization=plan_details.can_view_organization,
                enable_dialer=plan_details.enable_dialer,
                is_bulk_workflow_enabled=plan_details.is_bulk_workflow_enabled,
                can_view_mview_management=plan_details.can_view_mview_management,
                is_advance_filter_enabled=plan_details.is_advance_filter_enabled,
                can_view_template_management=plan_details.can_view_template_management,
                can_view_product_management=plan_details.can_view_product_management,
                can_view_finance_management=plan_details.can_view_finance_management,
                can_view_csf_lead_listing=plan_details.can_view_csf_lead_listing,
                is_teams_enabled=plan_details.is_teams_enabled,
                is_team_data_partition_enabled=plan_details.is_team_data_partition_enabled,
                can_view_products=plan_details.can_view_products,
                can_view_inventory=plan_details.can_view_inventory,
                can_view_order_management=plan_details.can_view_order_management,
                is_partner_custom_roles_enabled=plan_details.is_partner_custom_roles_enabled,
                is_user_tracker_enabled=plan_details.is_user_tracker_enabled,
                can_view_payment_history=plan_details.can_view_payment_history,
                is_reenquiry_chain_enabled=plan_details.is_reenquiry_chain_enabled,
                can_view_report_management=plan_details.can_view_report_management,
                can_view_helpdesk_management=plan_details.can_view_helpdesk_management,
                can_download_call_logs=plan_details.can_download_call_logs,
                is_inbox_enabled=plan_details.is_inbox_enabled,
                is_field_tracking_enabled=plan_details.is_field_tracking_enabled,
                can_view_inactive_agents=plan_details.can_view_inactive_agents,
                is_agent_availability_based_assignment_enabled=plan_details.is_agent_availability_based_assignment_enabled,
                is_sticky_dids_enabled=plan_details.is_sticky_dids_enabled,
                can_add_address_with_google_places=plan_details.can_add_address_with_google_places,
                is_assignee_sync_enabled=plan_details.is_assignee_sync_enabled,
            )
            return response

        except Exception as exc:
            self.__logger.error(
                f"Error occurred while getting partner: {partner_id} plan details, error: {exc}"
            )
            raise GrpcException(
                details="RPCExceptionMsg.ERROR_MSG",
                status_code=StatusCode.INTERNAL,
            )
