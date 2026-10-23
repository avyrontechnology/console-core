from uuid import UUID
import os
import unittest

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.core.app_env import AppEnvironment
from src.core.container import Container, UserService
from src.core.db import Base
from src.exceptions import EnvironmentNotFoundException

from .models import Contracts


# sample test case for the setup
class TestService(unittest.IsolatedAsyncioTestCase):
    def setUp(self, db=Depends(Provide[Container.db])) -> None:
        if (
            os.getenv("Env", AppEnvironment.AllowedEnvs.Testing.value)
            == AppEnvironment.AllowedEnvs.Testing.value
        ):
            engine = db._MySqlDB__master_engine
            Base.metadata.create_all(bind=engine)
            insert_row_user_property = """
                insert into userproperties (user_id, company_name, country_of_operation_id, city, country, zipcode, state, address, address2, is_terms_accepted, kyc_enabled, is_testing_agent) values (1, 'AdityaTest', 1, 'Noida', 'India', '800002', 'UP', 'test1', 'test2', True, True, True)
            """
            insert_row_auth_user = """
                insert into user (first_name, last_name, email, contact_number, language, is_active, username) values ('prince', 'kumar', 'aditya@gmail.com', '918299', 'en-us', 'true', 'aditya@gmail.com')
            """
            engine.execute(insert_row_user_property)
            engine.execute(insert_row_auth_user)
        else:
            raise EnvironmentNotFoundException("testing")

    @inject
    async def test_get_account_details_with_user_id(
        self,
        console_service: UserService = Depends(Provide[Container.console_service]),
    ):
        # test for valid case
        response = console_service.get_user_details(user_id= UUID("11111111-1111-1111-1111-111111111111"))
        self.assertEqual(response.id, 1)
        self.assertEqual(response.company_name, "AdityaTest")
        self.assertEqual(type(response), Contracts.AccountDetailsResponse)

        # test for invalid case (data not available in DB)
        response = console_service.get_account_details(user_id= UUID("10010010-0100-1001-0010-010010010010"))
        self.assertEqual(type(response), type(None))

    @inject
    def tearDown(self, db=Depends(Provide[Container.db])) -> None:
        if (
            os.getenv("Env", AppEnvironment.AllowedEnvs.Testing.value)
            == AppEnvironment.AllowedEnvs.Testing.value
        ):
            Base.metadata.drop_all(bind=db._MySqlDB__master_engine)
