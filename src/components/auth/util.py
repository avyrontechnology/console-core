from datetime import datetime, timedelta

import jwt
from fastapi import Request
from passlib.context import CryptContext

from src.components.auth.constant import TokenKeys
from src.components.common.response import UnauthorizedResponse
from src.core.environment import ENV
from src.loggers.console_service_logger import ConsoleServiceLogger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# get .env values
SECRET_KEY = ENV.SECRET_KEY
ALGORITHM = ENV.ALGORITHM


class AuthUtility:

    def __init__(self, console_service_logger: ConsoleServiceLogger):
        self.__user_logger = console_service_logger

    @staticmethod
    async def get_current_user(request: Request) -> dict:
        """
        This function return current user Token payload
        """
        if request.state.user is None:
            raise UnauthorizedResponse(detail="Unauthorized User")
        return request.state.user

    async def verify_password(self, plain_password: str, hash_password: str) -> bool:
        self.__user_logger.info("Verifying hash_password with plain password")
        return pwd_context.verify(plain_password, hash_password)

    async def get_password_hash(self, password: str) -> str:
        self.__user_logger.debug("Hashing password...")
        return pwd_context.hash(password)

    async def create_access_token(
        self, data: dict, expires_delta: timedelta = None
    ) -> str:
        self.__user_logger.info("Creating access token")
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=15
            )  # create function for exp.
        to_encode.update({TokenKeys.EXPIRED: expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    def decode_access_token(self, token: str) -> dict:
        self.__user_logger.debug("Decoding access token...")
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=ALGORITHM)
            self.__user_logger.debug("Access token decoded successfully.")
            return payload
        except jwt.ExpiredSignatureError:
            self.__user_logger.error("Access token has expired")
            return None
        except jwt.InvalidTokenError:
            self.__user_logger.error("Invalid access token")
            return None

    def decode_access_token_without_exp(self, token: str) -> dict:
        """Method will decode JWT Token without verifying the expiry time"""
        self.__user_logger.debug("Decoding Access Token without exp verification")
        try:
            payload = jwt.decode(
                token, SECRET_KEY, algorithms=ALGORITHM, options={"verify_exp": False}
            )
            return payload
        except jwt.InvalidTokenError:
            self.__user_logger.error("Invalid Access Token")
            return None
        except jwt.PyJWTError as error:
            self.__user_logger.error(f"Got an unexpected Error : {error}")
            return None
