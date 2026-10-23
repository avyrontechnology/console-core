from uuid import UUID
import pytest
from pydantic import ValidationError

from src.components.partner.schema import (BasePartnerData, PartnerDetails,
                                           PartnerFilterRequest,
                                           PartnerMetaDataDetails,
                                           PartnerOnboardingDetails,
                                           PartnerOnboardingResponse,
                                           TogglePartnerActivation,
                                           TogglePartnerActivationResponse,
                                           UpdatePartnerRequest, UserDetails)
from src.components.payment.enum import PaymentBillingCycle


def test_base_partner_data_gst_cin_validation():
    # Invalid GST
    with pytest.raises(ValidationError):
        BasePartnerData(name="A", company_legal_name="B", gst_no="invalidgst")

    # Invalid CIN
    with pytest.raises(ValidationError):
        BasePartnerData(name="A", company_legal_name="B", cin_no="invalidcin")

    # Valid data
    partner = BasePartnerData(name="A", company_legal_name="B")
    assert partner.active_license == 3


def test_base_partner_data_description_length_validation():
    # Description over the 256-char DB column limit is rejected at validation
    # time (400) instead of blowing up as a 500 on the DB insert.
    with pytest.raises(ValidationError):
        BasePartnerData(name="A", company_legal_name="B", description="x" * 257)

    # Exactly at the limit is still accepted
    partner = BasePartnerData(
        name="A", company_legal_name="B", description="x" * 256
    )
    assert len(partner.description) == 256

    # Same guard applies on the update path
    with pytest.raises(ValidationError):
        UpdatePartnerRequest(description="x" * 257)


def test_update_partner_billing_cycle_validation():
    # Valid billing_cycle
    update = UpdatePartnerRequest(billing_cycle=PaymentBillingCycle.MONTHLY)
    assert update.billing_cycle == PaymentBillingCycle.MONTHLY

    # Invalid billing_cycle
    with pytest.raises(ValidationError):
        UpdatePartnerRequest(billing_cycle="INVALID_CYCLE")


def test_user_details_password_validation():
    # Invalid password
    with pytest.raises(ValidationError):
        UserDetails(
            name="Test",
            email="a@b.com",
            phone_number="+911234567890",
            password="weakpass",
        )

    # Valid password
    user = UserDetails(
        name="Test",
        email="a@b.com",
        phone_number="+911234567890",
        password="Strong1@pass",
    )
    assert user.password == "Strong1@pass"


def test_partner_filter_request_id_validation():
    # Non-numeric ID
    with pytest.raises(ValidationError):
        PartnerFilterRequest(filters=[{"field": "id", "operator": "=", "value": "abc"}])

    # Negative ID
    with pytest.raises(ValidationError):
        PartnerFilterRequest(filters=[{"field": "id", "operator": "=", "value": -5}])

    # ID exceeds max
    with pytest.raises(ValidationError):
        PartnerFilterRequest(filters=[{"field": "id", "operator": "=", "value": 9999999999}])


def test_partner_onboarding_details():
    partner_details = PartnerDetails(name="A", company_legal_name="B")
    partner_meta_data = PartnerMetaDataDetails()
    user_details = UserDetails(
        name="User",
        email="u@test.com",
        phone_number="+911234567890",
        password="Strong1@pass",
    )

    onboarding = PartnerOnboardingDetails(
        partner_details=partner_details,
        partner_meta_data=partner_meta_data,
        user_details=user_details,
    )

    assert onboarding.partner_details.name == "A"
    assert onboarding.user_details.email == "u@test.com"

def test_partner_onboarding_response_optional_token():
    response = PartnerOnboardingResponse(
        name="A",
        company_legal_name="B",
        id= UUID("11111111-1111-1111-1111-111111111111"),
        user_login_token="token123",
    )
    assert response.user_login_token == "token123"

    response_no_token = PartnerOnboardingResponse(
        name="A",
        company_legal_name="B",
        id= UUID("11111111-1111-1111-1111-111111111111"),
    )
    assert response_no_token.user_login_token is None


def test_toggle_partner_activation_defaults():

    toggle = TogglePartnerActivation()
    assert toggle.is_active is False

    resp = TogglePartnerActivationResponse(is_active=True)
    assert resp.is_active is True
