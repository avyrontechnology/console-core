from pydantic_settings import BaseSettings
from typing import List

class LocalSettings(BaseSettings):
    # database_url: "postgresql+asyncpg://jaggerbomb:jaggerbomb@user-db/userservice"
    echo_sql: bool = True
    test: bool = False
    project_name: str = "My FastAPI project"
    log_level: str = "DEBUG"
    # telecom_service = "TOCOM"
    redis_host: str = "console-redis"
    redis_port: int = 6379
    redis_password: str = "pwd"

    mongo_db: str  
    mongo_user: str  
    mongo_password: str 
    mongo_host: str 
    mongo_port: int

    cors_allow_origins: str | None = None
    allowed_hosts: str | None = None

    def cors_origins_list(self) -> List[str]:
        if not self.cors_allow_origins:
            return []
        return [origin.strip() for origin in self.cors_allow_origins.split(";") if origin.strip()]

    def allowed_hosts_list(self) -> List[str]:
        if not self.allowed_hosts:
            return []
        return [host.strip() for host in self.allowed_hosts.split(";") if host.strip()]


class ProdSettings(BaseSettings):
    echo_sql: bool = False


local_settings = LocalSettings()
prod_settings = ProdSettings()
