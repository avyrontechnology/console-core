from typing import Any, Dict, Optional

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator


class ApiRequestLog(BaseModel):
    request_method: str
    request_url: str
    request_headers: Dict[str, Any]
    request_body: Optional[Any]  = None


class ApiResponseLog(BaseModel):
    response_status_code: int
    # Any to match ApiRequestLog.request_body. Non-JSON endpoints (HTML pages
    # like /oauth/bridge, plain text, raw decoded fallback in the logging
    # middleware) return a str here; binary responses are pre-coerced to a
    # placeholder dict. Restricting this to dict caused every non-JSON
    # response to spam an ERROR-level "API log persistence failed: 1
    # validation error" line while the HTTP response itself had already
    # gone out fine. filter_sensitive_data() and mask_sensitive_fields()
    # already short-circuit on non-(dict|list) values, so widening here is
    # safe end-to-end.
    response_body: Optional[Any] = None
    response_time: float


class ApiLogResponse(BaseModel):
    id: str = Field(alias="_id")
    log_id: str
    client_ip: Optional[str] = None
    request: Optional[Dict[str, Any]] = None
    response: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None

    @field_validator("id", mode="before")
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        populate_by_name = True


class ApiLog(BaseModel):
    log_id: str
    ip_address: Optional[str] = None
    request: ApiRequestLog
    response: ApiResponseLog
    timestamp: float

    @classmethod
    def filter_sensitive_data(cls, data: dict) -> dict:
        SENSITIVE_KEYS = {"password", "access_token", "token", "authorization", "current_password", "new_password"}

        def mask_sensitive_fields(obj: Any) -> Any:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key.lower() in SENSITIVE_KEYS:
                        obj[key] = "***MASKED***"
                    else:
                        obj[key] = mask_sensitive_fields(value)
                return obj
            elif isinstance(obj, list):
                for i in range(len(obj)):
                    obj[i] = mask_sensitive_fields(obj[i])
                return obj
            return obj

        req = data.get("request", {})

        if headers := req.get("request_headers"):
            mask_sensitive_fields(headers)

        if body := req.get("request_body"):
            mask_sensitive_fields(body)

        if resp_body := data.get("response", {}).get("response_body"):
            mask_sensitive_fields(resp_body)

        return data
