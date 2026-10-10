from db_queries import DBManager

# update roles here for generating roles in db
ROLES = [("admin", 1), ("manager", 4), ("agent", 8)]


class RoleGenerator:
    def __init__(self) -> None:
        self.db: DBManager = DBManager()

    def run(self):
        self.db.save_roles(ROLES)


if __name__ == "__main__":
    role_generator: RoleGenerator = RoleGenerator()
    role_generator.run()
