from uuid import UUID

import pytest

from src.components.order.controllers import _parse_partner_ids

P1 = "11111111-1111-1111-1111-111111111111"
P2 = "22222222-2222-2222-2222-222222222222"


class TestParsePartnerIds:
    def test_none_returns_none(self):
        assert _parse_partner_ids(None) is None

    def test_single_uuid(self):
        assert _parse_partner_ids(P1) == [UUID(P1)]

    def test_json_list_of_uuids(self):
        assert _parse_partner_ids(f'["{P1}","{P2}"]') == [UUID(P1), UUID(P2)]

    def test_whitespace_is_stripped(self):
        assert _parse_partner_ids(f"  {P1}  ") == [UUID(P1)]

    def test_legacy_integer_is_rejected(self):
        with pytest.raises(ValueError):
            _parse_partner_ids("1")

    def test_malformed_uuid_is_rejected(self):
        with pytest.raises(ValueError):
            _parse_partner_ids("not-a-uuid")

    def test_empty_list_is_rejected(self):
        with pytest.raises(ValueError):
            _parse_partner_ids("[]")

    def test_list_of_non_uuid_is_rejected(self):
        with pytest.raises(ValueError):
            _parse_partner_ids("[1,2]")