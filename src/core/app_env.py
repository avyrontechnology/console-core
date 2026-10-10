import enum
import os

from src.exceptions import EnvironmentNotFoundException


class AppEnvironment:
    class AllowedEnvs(enum.Enum):
        Dev = "dev"
        Local = "local"
        Testing = "testing"
        Staging = "staging"
        Production = "production"

    def get_env_config_file_path(self):
        current_env = self.get_current_env()
        print("#----------- Env: ", current_env.value, "-----------#")
        # Return relavent env values.
        # return os.path.join(
        #     os.path.dirname(__file__), f"../env_config/{current_env.value}.json"
        # )

    def get_current_env(self) -> AllowedEnvs:
        current_env = os.getenv("Env", self.AllowedEnvs.Dev.value)

        if current_env not in [env.value for env in self.AllowedEnvs]:
            raise EnvironmentNotFoundException(current_env)
        else:
            return self.AllowedEnvs(current_env)
