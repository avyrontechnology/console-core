import os
from pathlib import Path

from dotenv import load_dotenv

from src.core.environment import ENV

from .settings import local_settings, prod_settings

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / ".env"
dotenv_path = os.path.join(os.path.dirname(__file__), ENV_PATH)
load_dotenv(dotenv_path)

if ENV.ENVIRONMENT == "PROD":
    settings = prod_settings
else:
    settings = local_settings
