from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PartnerMetadata(BaseModel):
    type_of_business: Optional[str] = Field(None, min_length=3, max_length=64)
    years_in_business: Optional[int] = 0
    annual_revenue: Optional[int] = 0
    is_maglo_enabled: Optional[bool] = False
    is_talko_enabled: Optional[bool] = False
    is_babbler_enabled: Optional[bool] = False


class UpdatePartnerMetaData(PartnerMetadata):
    pass


class PartnerMetaDataResponse(PartnerMetadata):
    id: int
    maglo_trail_expiry_time: Optional[int] = None
    talko_trail_expiry_time: Optional[int] = None
    babbler_trail_expiry_time: Optional[int] = None
    maglo_app_trail_expiry_time: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True,
    )

    @field_validator("type_of_business", mode="before")
    def default_type_of_business(cls, v):
        return v or None

    @field_validator("years_in_business", "annual_revenue", mode="before")
    def default_int_fields(cls, v):
        return v or 0

    @field_validator(
        "is_maglo_enabled", "is_talko_enabled", "is_babbler_enabled", mode="before"
    )
    def default_bool_fields(cls, v):
        return v if v is not None else False


class PartnerPlanDetailsResponse(BaseModel):
    is_maglo_service_enabled: Optional[bool] = False
    is_maglo_service_free_trial_enabled: Optional[bool] = False
    is_talko_service_enabled: Optional[bool] = False
    is_talko_service_free_trial_enabled: Optional[bool] = False
    is_babbler_service_enabled: Optional[bool] = False
    is_babbler_service_free_trial_enabled: Optional[bool] = False
    can_create_deals: Optional[bool] = False
    can_add_workflow: Optional[bool] = False
    can_view_workflow: Optional[bool] = False
    is_wallet_enabled: Optional[bool] = True
    email_config_key: Optional[str] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[str] = None
    is_maglo_app_enabled: Optional[bool] = False
    is_maglo_app_free_trial_enabled: Optional[bool] = False
    is_mailer_enabled: Optional[bool] = False
    is_gsm_calling_enabled: Optional[bool] = False
    can_view_task_management: Optional[bool] = False
    is_meeting_log_enabled: Optional[bool] = False
    subscription_mode: Optional[str] = None
    is_rule_based_assignment_enabled: Optional[bool] = False
    can_view_contact: Optional[bool] = False
    can_view_organization: Optional[bool] = False
    enable_dialer: Optional[bool] = False
    is_bulk_workflow_enabled: Optional[bool] = False
    can_view_mview_management: Optional[bool] = False
    is_advance_filter_enabled: Optional[bool] = False
    can_view_template_management: Optional[bool] = False
    can_view_product_management: Optional[bool] = False
    can_view_finance_management: Optional[bool] = False
    is_add_number_enabled: Optional[bool] = False
    is_obotaai_enabled: Optional[bool] = False
    is_teams_enabled: Optional[bool] = False
    is_team_data_partition_enabled: Optional[bool] = False
    can_view_products: Optional[bool] = False
    can_view_inventory: Optional[bool] = False
    can_view_order_management: Optional[bool] = False
    is_partner_custom_roles_enabled: Optional[bool] = False
    is_user_tracker_enabled: Optional[bool] = False
    can_view_payment_history: Optional[bool] = False
    is_reenquiry_chain_enabled: Optional[bool] = False
    can_view_report_management: Optional[bool] = False
    can_view_helpdesk_management: Optional[bool] = False
    can_download_call_logs: Optional[bool] = False
    can_view_inactive_agents: Optional[bool] = False
    is_agent_availability_based_assignment_enabled: Optional[bool] = False
    is_sticky_dids_enabled: Optional[bool] = False
    can_add_address_with_google_places: Optional[bool] = False
    is_assignee_sync_enabled: Optional[bool] = False

    model_config = ConfigDict(
        from_attributes=True,
        extra="allow",
    )
