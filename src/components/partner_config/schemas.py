from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

from src.components.partner_config.constants import SubscriptionModeEnum


class PartnerConfigBase(BaseModel):
    key: str
    value: Optional[Union[int, str, dict, list, bool]] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class PartnerConfigRequest(BaseModel):
    key: str
    value: Optional[Union[int, str, dict, list, bool]] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class PartnerConfigResponse(BaseModel):
    id: Optional[int] = None
    key: Optional[str] = None
    value: Optional[Union[int, str, dict, list, bool]] = None
    partner_id: Optional[int] = None
    created_at: Optional[int] = None
    history: Optional[list] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class UpdatePartnerConfigResponse(PartnerConfigResponse):
    updated_at: int
    updated_by: int
    id: Optional[int] = None
    key: Optional[str] = None
    value: Optional[Union[int, str, dict, list]] = None
    history: Optional[list] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class PartnerConfigUpdateRequest(BaseModel):
    new_value: Optional[Union[int, str, dict, list, bool]] = None


class PartnerConfigData(BaseModel):
    is_custom_role_permission_enabled: Optional[bool] = False
    is_maglo_enabled: Optional[bool] = None
    is_talko_enabled: Optional[bool] = False
    is_babbler_enabled: Optional[bool] = False
    is_otp_enabled: Optional[bool] = False
    send_user_credentials: Optional[bool] = False
    is_email_verification_enabled: Optional[bool] = False
    can_create_deals: Optional[bool] = False
    can_add_workflow: Optional[bool] = False
    can_view_workflow: Optional[bool] = False
    is_wallet_enabled: Optional[bool] = True
    is_maglo_app_enabled: Optional[bool] = False
    is_babbler_app_enabled: Optional[bool] = False
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[str] = None
    is_mailer_enabled: Optional[bool] = False
    is_gsm_calling_enabled: Optional[bool] = False
    can_view_task_management: Optional[bool] = False
    is_meeting_log_enabled: Optional[bool] = False
    subscription_mode: Optional[str] = None
    is_rule_based_assignment_enabled: Optional[bool] = False
    can_view_pipeline_management: Optional[bool] = False
    is_complementary_babbler_enabled: Optional[bool] = False
    can_view_contact: Optional[bool] = False
    can_view_organization: Optional[bool] = False
    enable_dialer: Optional[bool] = False
    is_bulk_workflow_enabled: Optional[bool] = False
    is_obotaai_enabled: Optional[bool] = False
    can_view_mview_management: Optional[bool] = False
    is_advance_filter_enabled: Optional[bool] = False
    can_view_template_management: Optional[bool] = False
    can_view_product_management: Optional[bool] = False
    can_view_finance_management: Optional[bool] = False
    can_view_csf_lead_listing: Optional[bool] = False
    is_add_number_enabled: Optional[bool] = False
    can_view_products: Optional[bool] = False
    can_view_inventory: Optional[bool] = False
    can_view_order_management: Optional[bool] = False
    # Teams feature
    is_teams_enabled: Optional[bool] = None
    is_partner_custom_roles_enabled: Optional[bool] = None
    is_team_data_partition_enabled: Optional[bool] = None
    is_reenquiry_chain_enabled: Optional[bool] = False
    team_strict_hierarchy_mode: Optional[str] = None
    team_strict_hierarchy_start_role_id: Optional[int] = None
    is_user_tracker_enabled: Optional[bool] = False
    can_view_payment_history: Optional[bool] = False
    can_view_report_management: Optional[bool] = False
    can_view_helpdesk_management: Optional[bool] = False
    can_download_call_logs: Optional[bool] = False
    is_inbox_enabled: Optional[bool] = False
    is_field_tracking_enabled: Optional[bool] = False
    can_view_inactive_agents: Optional[bool] = False
    is_agent_availability_based_assignment_enabled: Optional[bool] = False
    is_sticky_dids_enabled: Optional[bool] = False
    can_add_address_with_google_places: Optional[bool] = False
    is_assignee_sync_enabled: Optional[bool] = False

    @field_validator("subscription_mode")
    @classmethod
    def validate_subscription_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = [e.value for e in SubscriptionModeEnum]
        if v not in allowed:
            raise ValueError(
                "subscription_mode must be one of: {}".format(", ".join(allowed))
            )
        return v


class EmailConfigUpsertSchema(BaseModel):
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[EmailStr] = None

    @model_validator(mode="before")
    def field_check(cls, values):
        if not any(values.values()):
            raise ValueError(
                "At least one field must be provided: smtp_username, smtp_password, from_email"
            )
        return values
