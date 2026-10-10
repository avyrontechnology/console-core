import sys
from typing import List

from db_queries import DBManager
from dotenv import load_dotenv

load_dotenv()
# update methods name of controllers here for generating permissions in db
CONSOLE_PERMISSIONS = [
    "create_permission",
    "create_role",
    "delete_permission",
    "delete_roles",
    "get_all_permission",
    "get_permission_by_id",
    "get_role_by_id",
    "get_roles",
    "logout",
    "add_partner_address",
    "delete_partner_address_by_id",
    "get_partner_address",
    "get_partner_address_by_id",
    "get_digital_assets",
    "upload_digital_asset",
    "add_partner",
    "delete_partner",
    "get_all_partners",
    "get_partners_by_id",
    "update_partner",
    "delete_user",
    "get_all_users",
    "get_users_by_partner_id",
    "update_user",
    "add_partner_role_permission",
    "delete_partner_role_permission",
    "get_partner_role_permission_by_id",
    "get_prp_by_partner_id",
    "add_user_metadata",
    "delete_user_metadata",
    "get_user_metadata_by_user_id",
    "get_users_metadata",
    "update_user_metadata",
    "create_partner_metadata",
    "get_by_partner_id",
    "update_partner_meta_data",
    "get_all_countries",
    "get_states_by_country",
    "get_cities_by_state",
    "bulk_refer_leads",
    "get_parent_users_by_role_id",
    "get_partner_statuses",
    "change_partner_status",
    "get_partner_meta_data",
    "get_partner_address_by_partner_id",
    "get_user_by_user_id",
    "get_admin_details_by_partner_id",
    "assume_user",
    "add_default_role_permission",
    "delete_default_role_permission_by_id",
    "create_partner_config",
    "get_partner_config_by_key",
    "update_partner_config",
]

MAGLO_PERMISSIONS = [
    "create_service_board_user",
    "delete_service_board_user",
    "get_service_board_user",
    "get_lead_sources",
    "get_leads_count_by_partner_source_id",
    "get_agents_detail",
    "create_partner_section_mapping",
    "get_custom_fields_by_section_and_service_board",
    "get_sections_by_service_board",
    "bulk_lead_creation",
    "create_lead_and_lead_source",
    "dashboard_cards",
    "get_lead_custom_fields",
    "get_lead_homepage_cards",
    "get_lead_overview_cards",
    "get_personal_details",
    "get_reenquired_history",
    "get_source_details",
    "list_leads",
    "refer_lead",
    "search_lead",
    "update_lead_custom_fields",
    "create_service_journey",
    "create_service_journey_status",
    "create_service_journey_substatus",
    "get_statuses_by_service_board",
    "add_partner_lead_source",
    "get_partner_sources",
    "update_partner_source",
    "add_followup",
    "get_followups",
    "get_followups_by_lead_request_id",
    "update_followup",
    "create_section",
    "get_section",
    "get_sections_by_service_id",
    "update_section",
    "create_custom_field_metadata",
    "get_all_custom_fields",
    "get_lead_history",
    "get_lead_requests_by_lead_id",
    "update_lead_request",
    "create_service_board",
    "delete_service_board",
    "get_active_service_boards",
    "get_service_board",
    "create_business_domain",
    "get_business_domains",
    "get_all_service_board_configs",
    "update_service_board_config",
    "create_service_board_config",
    "get_service_board_config",
    "create_partner_config",
    "get_partner_config",
    "update_partner_config",
    "get_partner_configs_by_partner_id",
    "get_service_boards_by_channel_id",
    "get_channels_by_service_board_id",
    "create_channel",
    "update_channel",
    "delete_service_board_channel_association",
    "delete_channel",
    "create_external_lead_with_channel_key",
    "create_dropdown",
    "get_dropdown_values",
    "update_dropdown",
    "reset_to_previous_version",
    "home_page_details",
    "get_user_child_service_boards",
    "map_partner_publisher",
    "publisher_dashboard",
    "get_publisher_network_management",
    "get_publisher_feedback",
    "publisher_partners",
    "publisher_overview_cards",
    "list_publisher_leads",
    "get_publisher_data",
    "get_all_publishers",
    "clone_service_board",
    "get_all_service_boards",
    "delete_lead_file_custom_field",
    "delete_status_journey",
    "delete_sub_status_journey",
    "update_status_journey",
]


class PermissionGenerator:
    def __init__(self, app_name) -> None:
        self.app_name: str = sys.argv[1].strip().lower()
        self.db: DBManager = DBManager()

    def generate_permissions(self) -> List[str]:
        """Generates a list of permission names prefixed by the app name ."""
        if self.app_name == "maglo":
            return [f"{self.app_name}_{method}" for method in MAGLO_PERMISSIONS]
        elif self.app_name == "console":
            return [f"{self.app_name}_{method}" for method in CONSOLE_PERMISSIONS]
        return []

    def run(self) -> None:
        all_permissions: List[str] = self.generate_permissions()
        self.db.save_permissions(all_permissions)


if __name__ == "__main__":

    APP_NAME = "console"
    permission_generator: PermissionGenerator = PermissionGenerator(app_name=APP_NAME)
    permission_generator.run()
