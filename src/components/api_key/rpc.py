import json

from src.pub.api_key_service_pb2 import ValidateApiKeyRequest, ValidateApiKeyResponse, GetApiKeyPartnerIdRequest, PartnerApiKeyResponse
from src.pub.api_key_service_pb2_grpc import ApiKeyServiceServicer
from dependency_injector.wiring import Provide, inject
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException
from fastapi import Depends
from src.core.container import Container
from src.components.api_key.services import ApiKeyNotFoundError, ApiKeyResponse, ApiKeyService
from src.components.common.rpc_uuid import parse_uuid, uuid_str


class ApiKeyServiceGRPC(ApiKeyServiceServicer):
    def __init__(self, logger):
        self.__logger = logger

    @inject
    async def ValidateApiKey(
        self,
        request: ValidateApiKeyRequest,
        context,
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
    ):
        api_key = request.key

        try:
            self.__logger.info(f"[gRPC]: Validating API key: {api_key[:10]}")

            key_details = await api_key_service.validate_api_key(api_key)

            if not key_details:
                self.__logger.warning(f"[gRPC]: Invalid API key: {api_key}")
                raise GrpcException(
                    details="Invalid or expired API key.",
                    status_code=StatusCode.UNAUTHENTICATED,
                )

            response = ValidateApiKeyResponse(
                id=uuid_str(key_details.id),
                key=key_details.key,
                partner_id=uuid_str(key_details.partner_id),
                is_active=key_details.is_active,
                scopes=list(key_details.scopes or []),
                user_context=json.dumps(key_details.user_context or {}),
            )

            self.__logger.info(f"[gRPC]: Successfully validated API key for partner_id: {key_details.partner_id}")
            return response

        except GrpcException:
            # Already handled custom gRPC exception, just re-raise
            raise
        except Exception as exc:
            self.__logger.error(f"[gRPC]: Error during API key validation: {exc}")
            raise GrpcException(
                details="Internal server error during API key validation.",
                status_code=StatusCode.INTERNAL,
            )


    @inject
    async def GetApiByPartnerId(
        self,
        request: GetApiKeyPartnerIdRequest,
        context,
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
    ):
        partner_id = parse_uuid(request.partner_id, "partner_id")

        try:
            self.__logger.info(f"[gRPC]: Fetching API key details for partner_id: {partner_id}")

            key_details: ApiKeyResponse = await api_key_service.get_api_key(partner_id=partner_id)
            
            response = PartnerApiKeyResponse(
                id=uuid_str(key_details.id),
                key=key_details.key,
                description=key_details.description,
                partner_id=uuid_str(key_details.partner_id),
                is_active=key_details.is_active,
            )

            self.__logger.info(
                f"[gRPC]: Retrieved API key for partner_id: {key_details.partner_id}"
            )
            return response
        except ApiKeyNotFoundError:
            raise GrpcException(
                details="API key not found.",
                status_code=StatusCode.NOT_FOUND,
            )
        except Exception as exc:
            self.__logger.error(f"[gRPC]: Error fetching API key: {exc}")
            raise GrpcException(
                details="Internal server error while fetching API key.",
                status_code=StatusCode.INTERNAL,
            )