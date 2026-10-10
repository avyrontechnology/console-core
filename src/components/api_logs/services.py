from src.components.api_logs.repositories import APILogRepository
from src.components.api_logs.schemas import ApiLog, ApiLogResponse
from src.loggers.console_service_logger import ConsoleServiceLogger


class APILogService:
    def __init__(
        self,
        api_log_repository: APILogRepository,
        console_service_logger: ConsoleServiceLogger,
    ):
        self.__api_log_repository = api_log_repository
        self.__console_service_logger = console_service_logger

    async def log_api(self, raw_log_data: dict):
        """
        Filter sensitive information and validate data using Pydantic DTO,
        then save the validated log document via the repository.
        """
        try:
            self.__console_service_logger.info("Attempting to insert the api logs.")
            filtered_data = ApiLog.filter_sensitive_data(raw_log_data)
            validated_log = ApiLog(**filtered_data)
            await self.__api_log_repository.save_log(validated_log)
        except Exception as exec:
            self.__console_service_logger.error(
                "Error occured while saving API log: {}".format(exec)
            )
            raise exec

    async def get_api_log_by_log_id(self, log_id: str) -> list[ApiLogResponse]:
        """
        Fetch API log by its log_id, validate, and serialize for response.
        """
        try:
            self.__console_service_logger.info(
                "Attempting to retrieve API log for log_id: {}".format(log_id)
            )
            api_log = await self.__api_log_repository.get_api_logs_by_log_id(log_id)
            if not api_log:
                self.__console_service_logger.warning(
                    "No API log found for log_id: {}".format(log_id)
                )
                return []
            # Validate and serialize with Pydantic
            validated_log = ApiLogResponse.model_validate(api_log)
            self.__console_service_logger.info(
                "Successfully validated API log for log_id: {}".format(log_id)
            )
            return [validated_log.model_dump(by_alias=True)]
        except Exception as exec:
            self.__console_service_logger.error(
                "Error retrieving API log for log_id={}: {}".format(log_id, exec)
            )
            raise exec
