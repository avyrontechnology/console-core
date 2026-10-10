from typing import Any

from src.components.api_logs.schemas import ApiLog
from src.components.database.model_config import TABLES
from src.core.mongo_db import MongoDatabaseSessionManager
from src.loggers.console_service_logger import ConsoleServiceLogger


class APILogRepository:
    def __init__(
        self,
        mongo_db_session: MongoDatabaseSessionManager,
        logger: ConsoleServiceLogger,
    ):
        self.__mongo_db_session = mongo_db_session
        self.__console_service_logger = logger

    async def save_log(self, api_log_data: ApiLog):
        """
        Persist the validated API log document into the 'api_logs' collection in MongoDB.
        """
        try:
            async with self.__mongo_db_session.collection(
                TABLES.API_LOGS
            ) as collection:
                self.__console_service_logger.info(
                    "Inserting the api logs into database..."
                )
                await collection.insert_one(api_log_data.dict())
                self.__console_service_logger.info(
                    "Api logs successfully inserted into the database: {}".format(
                        api_log_data
                    )
                )
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while inserting the api logs into the database: {}".format(
                    exec
                )
            )
            raise exec

    async def get_api_logs_by_log_id(self, log_id: str) -> Any | None:
        """
        Fetch a single API log document from MongoDB by its unique log_id.
        """
        try:
            async with self.__mongo_db_session.collection(
                TABLES.API_LOGS
            ) as collection:
                self.__console_service_logger.info(
                    "Fetching API log from database for log_id: {}".format(log_id)
                )

                api_log = await collection.find_one({"log_id": log_id})

                if not api_log:
                    self.__console_service_logger.warning(
                        "No API log found in database for log_id: {}".format(log_id)
                    )
                    return None

                self.__console_service_logger.info(
                    "Successfully fetched API log for log_id: {}".format(log_id)
                )
                return api_log

        except Exception as exec:
            self.__console_service_logger.error(
                "Error fetching API log for log_id={}: {}".format(log_id, exec)
            )
            raise exec
