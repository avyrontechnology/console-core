from fastapi import APIRouter, FastAPI
import logging

from src.components.db_constants.initializer import (
    ConstantsCreator,
    ConstantsInitializer,
)
from src.components.security.robots import RobotsController

from src.config.swagger import SwaggerConfig

from src.core.container import Container

from src.core.firebase import firebase_init
from src.exceptions.validation import handler
from src.middlewares import allowed_middlewares
from src.routes.base import Router
import firebase_admin
from firebase_admin import credentials
import json
from src.components.notifications.constants import NotificationServiceType


container = Container()
container.check_dependencies()

app = FastAPI(
    title="Obotaai Console API's",
    container=container,
    middleware=allowed_middlewares,
)

console_service = APIRouter(prefix="/console-service/v1")


Router.register_all_routes(console_service)

app.include_router(console_service)
# app.include_router(console_service, prefix="/service")

# ── RFC-8414 / RFC-9728 spec-compliant OAuth discovery (root-mounted) ────
# Both specs build the well-known URL by INSERTING /.well-known/<name>
# between the host and the issuer/resource path. With our issuer set to
# ``https://<host>/console-service/v1`` that means spec-strict clients
# (Claude.ai Custom Connectors) compute discovery URLs at:
#   /.well-known/oauth-authorization-server/console-service/v1
#   /.well-known/oauth-protected-resource/console-service/v1
# These live at the host root, NOT under the /console-service/v1 prefix.
# Routes return the same JSON as their prefixed counterparts (see
# ``OAuthController._build_*_metadata``); we keep both flavours so naive
# clients that follow our explicit WWW-Authenticate URL also work.
try:
    from src.components.oauth_server import config as _oauth_cfg
    from src.components.oauth_server.controllers import (
        OAuthController as _OAuthController,
    )

    if _oauth_cfg.OAUTH_ENABLED:
        app.include_router(
            _OAuthController.well_known_root_router,
            tags=["OAuth Discovery (RFC 8414)"],
        )
except Exception:  # pragma: no cover — keep boot resilient if OAuth is off
    pass

# Apply Swagger configuration
SwaggerConfig.get_swagger_config(app)

# add validation exception handler
handler(app)

# add robots.txt router
app.include_router(RobotsController.robot_router)

# Clear root logger handlers to avoid duplicate/default logs
logging.getLogger().handlers.clear()

session_factory = container.db().session


@app.on_event("startup")
async def startup_event():
    print(
        "//////////////////////////// initializing constants... ////////////////////////////"
    )
    await ConstantsCreator.create_constants(session_factory)
    await ConstantsInitializer.initialize_constants(session_factory)
    print(
        "//////////////////////////// Constants initialized. ////////////////////////////"
    )

    try:
        # Initialize Maglo Firebase
        firebase_init(NotificationServiceType.MAGLO)

        # Initialize Babbler Firebase
        firebase_init(NotificationServiceType.BABBLER)

        print(
            "//////////////////////////// Firebase initialized for Maglo and Babbler ////////////////////////////"
        )
    except Exception as e:
        print(f"//////////////////////////// Firebase initialization failed: {e} ////////////////////////////")
