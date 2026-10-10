from collections import namedtuple
from unittest.mock import Mock

from src.components.partner_meta_data.schema import UpdatePartnerMetaData
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.components.unit_test.base_test import BaseTestSetup
from src.core.db import Base
from src.exceptions import PartnerMetaDataException


class TestPartnerMetaDataService(BaseTestSetup):

    async def initialize_dependency(self) -> None:

        self.partner_metadata_service = PartnerMetaDataServices(
            partner_meta_data_repository=self.mock_db_session,
            console_service_logger=Mock(),
        )

        # Create a namedtuple to simulate the result of the query
        PartnerMetaDataRow = namedtuple(
            "PartnerMetaDataRow",
            [
                "id",
                "partner_id",
                "api_key",
                "timezone",
                "number_of_users",
                "primary_contact",
            ],
        )

        # Initialize the mock row
        self.mock_row = PartnerMetaDataRow(
            id=1,
            partner_id=1,
            api_key="5f715b8f-3ae7-4fce-a685-cc0f766359a5",
            timezone="utc",
            number_of_users=30,
            primary_contact="example@gmail.com",
        )

        # Mock data for UpdatePartnerMetaData
        self.update_data = UpdatePartnerMetaData(
            partner_id=1,
            timezone="UTC",
            number_of_users=100,
            primary_contact="updated_contact@example.com",
        )

    async def test_get_by_partner_id(self):
        self.mock_db_session.get_by_partner_id.return_value = self.mock_row
        response = await self.partner_metadata_service.get_by_partner_id(partner_id=1)
        self.assertEqual(response.id, 1)
        self.assertEqual(response.partner_id, 1)

    async def test_get_all_partner_meta_data(self):
        self.mock_db_session.get_all_partner_meta_data.return_value = [self.mock_row]
        response = await self.partner_metadata_service.get_all_partner_meta_data()
        self.assertIsInstance(response, list)

    async def test_update_partner_meta_data(self):
        self.mock_db_session.update_partner_meta_data.return_value = self.update_data
        response = await self.partner_metadata_service.update_partner_meta_data(
            partner_id=1, update_data=self.update_data
        )
        self.assertEqual(response, self.update_data)

    async def test_get_by_partner_id_exception(self):

        self.mock_db_session.get_by_partner_id.side_effect = PartnerMetaDataException(
            "Internal server error"
        )

        with self.assertRaises(PartnerMetaDataException):
            await self.partner_metadata_service.get_by_partner_id(partner_id=1)

    async def test_update_partner_meta_data_exception(self):
        self.mock_db_session.update_partner_meta_data.side_effect = (
            PartnerMetaDataException("Error updating metadata")
        )

        with self.assertRaises(PartnerMetaDataException):
            await self.partner_metadata_service.update_partner_meta_data(
                partner_id=1, update_data=self.update_data
            )

    async def test_get_all_partner_meta_data_exception(self):

        self.mock_db_session.get_all_partner_meta_data.side_effect = Exception(
            "Error fetching all metadata"
        )

        with self.assertRaises(Exception):
            await self.partner_metadata_service.get_all_partner_meta_data()

    async def test_get_by_partner_id_general_exception(self):

        self.mock_db_session.get_by_partner_id.side_effect = Exception(
            "Some unexpected error"
        )

        with self.assertRaises(Exception):
            await self.partner_metadata_service.get_by_partner_id(partner_id=1)

    async def test_update_partner_meta_data_general_exception(self):

        self.mock_db_session.update_partner_meta_data.side_effect = Exception(
            "Some unexpected error"
        )

        with self.assertRaises(Exception):
            await self.partner_metadata_service.update_partner_meta_data(
                partner_id=1, update_data=self.update_data
            )
