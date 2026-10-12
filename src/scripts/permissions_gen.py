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


class PermissionGenerator:
    def __init__(self, app_name) -> None:
        self.app_name: str = sys.argv[1].strip().lower()
        self.db: DBManager = DBManager()

    def generate_permissions(self) -> List[str]:
        """Generates a list of permission names prefixed by the app name ."""
        if self.app_name == "console":
            return [f"{self.app_name}_{method}" for method in CONSOLE_PERMISSIONS]
        return []

    def run(self) -> None:
        all_permissions: List[str] = self.generate_permissions()
        self.db.save_permissions(all_permissions)


if __name__ == "__main__":

    APP_NAME = "console"
    permission_generator: PermissionGenerator = PermissionGenerator(app_name=APP_NAME)
    permission_generator.run()
