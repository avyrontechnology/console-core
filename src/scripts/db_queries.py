import os
from datetime import datetime
from typing import List

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "userservice"),
    "user": os.getenv("POSTGRES_USER", "jaggerbomb"),
    "password": os.getenv("POSTGRES_PASSWORD", "jaggerbomb"),
    "host": os.getenv("POSTGRES_HOST", "console-db"),
    "port": os.getenv("POSTGRES_PORT", 5432),
}


class DBManager:

    def _get_connection(self):
        """Creates and returns a new database connection."""
        try:
            return psycopg2.connect(**DB_CONFIG)
        except Exception as exc:
            print(f"Getting error while connecting to db {exc}")
            raise exc

    def _execute_batch(self, query, data: List):
        """Executes a batch of SQL queries with the provided data."""
        try:
            conn = self._get_connection()
            with conn:
                with conn.cursor() as cursor:
                    cursor.executemany(query, data)
        except Exception as exc:
            print(f"Got an error while saving permissions Error: {exc}")
            raise exc

    @staticmethod
    def get_current_time() -> int:
        """Get the current time in milliseconds."""
        dt = datetime.now()
        return int(dt.timestamp() * 1000)

    def save_permissions(self, permissions: List):
        """
        Saves the generated permissions to the database.
        """
        if not permissions:
            print("No Permissions to save")
            return

        query = """
        INSERT INTO console_permission (title, slug, created_at, is_active, is_deleted)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (slug) 
        DO UPDATE SET 
            title = EXCLUDED.title,
            is_active = EXCLUDED.is_active,
            is_deleted = EXCLUDED.is_deleted;
        """
        created_at = self.get_current_time()
        print("Saving Permissions in db..")
        self._execute_batch(
            query,
            [
                (permission, permission, created_at, True, False)
                for permission in permissions
            ],
        )

        print(f"Saved {len(permissions)} permissions to the database.")

    def save_permissions_new(self, permissions: List[dict]):
        """
        Saves the generated permissions to the database.
        Each permission must include: title, slug, category, display_text.
        """
        if not permissions:
            print("No Permissions to save")
            return

        query = """
        INSERT INTO console_permission (title, slug, category, display_text, created_at, is_active, is_deleted, is_internal)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (slug) 
        DO UPDATE SET 
            title = EXCLUDED.title,
            category = EXCLUDED.category,
            display_text = EXCLUDED.display_text,
            is_active = EXCLUDED.is_active,
            is_deleted = EXCLUDED.is_deleted,
            is_internal = EXCLUDED.is_internal;
        """

        created_at = self.get_current_time()
        print("Saving Permissions in db...")

        self._execute_batch(
            query,
            [
                (
                    perm["title"],
                    perm["slug"],
                    perm.get("category"),
                    perm.get("display_text"),
                    created_at,
                    True,
                    False,
                    perm.get("is_internal")
                )
                for perm in permissions
            ],
        )

        print(f"Saved {len(permissions)} permissions to the database.")

    def save_roles(self, roles):
        """Saves roles to the database."""

        if not roles:
            print("No roles to save.")
            return

        query = """
        INSERT INTO console_role (name, slug, hierarchy, created_at, is_active, is_deleted)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (slug) 
        DO UPDATE SET 
            name = EXCLUDED.name,
            hierarchy = EXCLUDED.hierarchy, 
            is_active = EXCLUDED.is_active,
            is_deleted = EXCLUDED.is_deleted;
        """
        created_at = self.get_current_time()
        print("Saving Roles in db..")
        self._execute_batch(
            query,
            [(role[0], role[0], role[1], created_at, True, False) for role in roles],
        )
        print(f"Saved {len(roles)} roles to the database.")

    def insert_location(self, countries, states, cities):
        created_at = self.get_current_time()
        country_query = """
        INSERT INTO console_countries (name, slug, created_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (slug) DO NOTHING;
        """
        self._execute_batch(
            country_query, [(c[0], c[1], created_at) for c in countries]
        )

        state_query = """
        INSERT INTO console_states (name, slug, country_id, created_at)
        VALUES (%s, %s, (SELECT id FROM console_countries WHERE slug = %s), %s)
        ON CONFLICT (slug) DO NOTHING;
        """
        self._execute_batch(
            state_query, [(s[0], s[1], s[2], created_at) for s in states]
        )

        city_query = """
        INSERT INTO console_cities (name, slug, state_id, created_at)
        VALUES (%s, %s, (SELECT id FROM console_states WHERE slug = %s), %s)
        ON CONFLICT (slug) DO NOTHING;
        """
        self._execute_batch(
            city_query, [(c[0], c[1], c[2], created_at) for c in cities]
        )
