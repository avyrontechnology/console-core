from fastapi import APIRouter, FastAPI
import logging

from src.components.db_constants.initializer import (
    ConstantsCreator,
    ConstantsInitializer,
)
from src.components.security.robots import RobotsController

from src.config.swagger import SwaggerConfig

from src.core.container import Container

from src.exceptions.validation import handler
from src.middlewares import allowed_middlewares
from src.routes.base import Router


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
        print(
            "//////////////////////////// Firebase disabled (no push services) ////////////////////////////"
        )
    except Exception as e:
        print(f"//////////////////////////// Firebase initialization failed: {e} ////////////////////////////")
