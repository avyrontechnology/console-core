import sys
from typing import List,Dict

from db_queries import DBManager
from dotenv import load_dotenv
from src.components.auth.permission_mapper import PermissionCategories
load_dotenv()


class PermissionGenerator:
    def __init__(self, app_name: str) -> None:
        self.app_name: str = app_name.strip().lower()
        self.db: DBManager = DBManager()

    def to_title_case(self, name: str) -> str:
        return name.replace("_", " ").title()

    def generate_permissions(self) -> List[Dict[str, str]]:
        """
        Generate full permission dicts with slug, title, category, display_text.
        """
        permissions = []

        if self.app_name == "console":
            source = PermissionCategories.CONSOLE_PERMISSIONS
        elif self.app_name == "talko":
            source = PermissionCategories.TALKO_PERMISSIONS
        elif self.app_name == "obotaai":
            source = PermissionCategories.OBOTAAI_PERMISSIONS
        else:
            print(f"Unknown app name: {self.app_name}")
            return []

        for category, methods in source.items():
            for method_name,is_internal in methods:
                slug = f"{self.app_name}:{method_name}"
                title = self.to_title_case(method_name)
                display_text = f"{title} ({category})"
                permissions.append({
                    "slug": slug,
                    "title": title,
                    "category": category,
                    "display_text": display_text,
                    "is_internal":is_internal
                })

        return permissions

    def run(self) -> None:
        all_permissions: List[Dict[str, str]] = self.generate_permissions()
        self.db.save_permissions_new(all_permissions)


if __name__ == "__main__":
    APP_NAME = sys.argv[1] if len(sys.argv) > 1 else "console"
    permission_generator = PermissionGenerator(app_name=APP_NAME)
    permission_generator.run()