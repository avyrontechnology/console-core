"""
Maps internal permission endpoints to
Platform → Modules → Features → Endpoints

Used for:
- Showing plan features on UI
- Determining what a user has access to
- Decoupling UI language from backend permission keys
"""

from src.components.plan.constants import Platform

SERVICE_FEATURE_MAPPER = {
    Platform.MAGLO: {
        # ================= DASHBOARD =================
        "Dashboard": {
            "Performance Overview": {
                "endpoints": ["dashboard_cards"],
                "flags": [],
            },
        },
        # ================= INSIGHT =================
        "Insight": {
            "Basic Insight": {
                "endpoints": [
                    "get_lead_insight_managerial_level",
                    "get_insight_lead_management_level",
                ],
                "flags": [],
            },
            "Call Insight": {
                "endpoints": ["get_analytics"],
                "flags": [],
            },
            "Advance Analytics": {
                "endpoints": [],
                "flags": [],
            },
        },
        # ================= LEAD =================
        "Lead": {
            "Create": {
                "endpoints": [
                    "create_lead_and_source",
                    "create_external_lead_with_channel_key",
                ],
                "flags": [],
            },
            "Auto Revive": {
                "endpoints": ["revive_lead_requests"],
                "flags": [],
            },
            "Re-enquired": {
                "endpoints": ["get_reenquired_history"],
                "flags": [],
            },
            "Lead History": {
                "endpoints": ["get_lead_history"],
                "flags": [],
            },
            "Refer Lead": {
                "endpoints": ["refer_lead"],
                "flags": [],
            },
            "Lead Sources": {
                "endpoints": ["get_partner_sources"],
                "flags": [],
            },
            "Lead Score": {
                "endpoints": [
                    "create_lead_score_config",
                    "get_config_by_event_type",
                    "update_lead_score_config",
                ],
                "flags": [],
            },
        },
        # ================= SERVICE BOARD =================
        "Service Board": {
            "Service Board Config": {
                "endpoints": ["get_all_service_board_configs"],
                "flags": [],
            },
            "Service Boards": {
                "endpoints": ["get_service_board"],
                "flags": [],
            },
            "Service Board Journey Status / Substatus": {
                "endpoints": [
                    "create_service_journey",
                    "create_service_journey_status",
                    "create_service_journey_substatus",
                ],
                "flags": [],
            },
        },
        # ================= BULK LEAD ACTIONS =================
        "Bulk Lead Actions": {
            "Assign": {
                "endpoints": ["reassign_lead_request"],
                "flags": [],
            },
            "Refer": {
                "endpoints": ["bulk_refer_leads"],
                "flags": [],
            },
            "Change Status / Substatus": {
                "endpoints": ["update_bulk_status_and_sub_status"],
                "flags": [],
            },
            "Revive": {
                "endpoints": ["bulk_revive_lead_request"],
                "flags": [],
            },
            "Download": {
                "endpoints": ["download_leads"],
                "flags": [],
            },
        },
        # ================= INTEGRATIONS =================
        "Integrations": {
            "WhatsApp": {
                "endpoints": ["send_message", "send_template"],
                "flags": [],
            },
            "Call": {
                "endpoints": ["initiate_call"],
                "flags": [],
            },
            "Email": {
                "endpoints": [
                    "send_mail",
                    "get_templates",
                    "create_template",
                    "update_template",
                    "delete_template",
                    "map_template_to_service_board",
                    "unmap_template_from_service_board",
                ],
                "flags": [],
            },
        },
        # ================= FOLLOWUP =================
        "Followup": {
            "Add Followup": {
                "endpoints": ["add_followup"],
                "flags": [],
            },
            "Mark Done / Reschedule / Cancel": {
                "endpoints": ["update_followup"],
                "flags": [],
            },
            "Followup Notification": {
                "endpoints": ["get_followups"],
                "flags": [],
            },
        },
        # ================= CALL =================
        "Call": {
            "Call Logs": {
                "endpoints": ["get_agent_call_logs"],
                "flags": [],
            },
            "Make Calls": {
                "endpoints": ["initiate_call"],
                "flags": [],
            },
            "Call Recording": {
                "endpoints": ["get_call_record_history"],
                "flags": [],
            },
        },
        # ================= PUBLISHER =================
        "Publisher": {
            "Publisher Onboarding": {
                "endpoints": ["add_partner", "map_partner_publisher"],
                "flags": [],
            },
        },
        # ================= CUSTOM =================
        "Custom": {
            "Custom Sections": {
                "endpoints": [
                    "create_section",
                    "update_section",
                ],
                "flags": [],
            },
            "Custom Fields": {
                "endpoints": [
                    "create_custom_field_metadata",
                    "get_all_custom_fields",
                ],
                "flags": [],
            },
        },
        # ================= AUTOMATION & INTEGRATIONS =================
        "Automation & Integrations": {
            "Meta Integration (FB & Instagram)": {
                "endpoints": ["workflow"],
                "flags": [],
            },
            "IVR": {
                "endpoints": [],
                "flags": [],
            },
            "Dialer": {
                "endpoints": ["initiate_call"],
                "flags": [],
            },
            "Chatbot": {
                "endpoints": [],
                "flags": [],
            },
            "Third party app integration": {
                "endpoints": [],
                "flags": [],
            },
        },
        # ================= MANAGEMENT =================
        "Management": {
            "Deal Management": {
                "endpoints": [
                    "create_deal",
                    "update_deal_by_id",
                    "get_deals_by_partner_id",
                    "get_deal_stages",
                    "enlist_deals_dynamically",
                ],
                "flags": [],
            },
            "Task Management": {
                "endpoints": [
                    "get_tasks",
                    "create_task",
                    "update_task_by_task_id",
                    "delete_task_by_task_ids",
                    "get_tasks_overview_cards",
                    "get_task_by_task_id",
                    "add_documents_to_task",
                ],
                "flags": [],
            },
            "Source Management": {
                "endpoints": [
                    "add_partner_lead_source",
                    "update_partner_source",
                    "get_partner_sources",
                ],
                "flags": [],
            },
            "Channel Management": {
                "endpoints": [
                    "create_channel",
                    "get_channels",
                    "get_channels_by_service_board_id",
                    "delete_service_board_channel_association",
                    "delete_channel",
                    "update_channel",
                ],
                "flags": [],
            },
        },
        # ================= APP =================
        "Mobile app": {
            "IOS": {
                "endpoints": [],
                "flags": [],
            },
            "Android": {
                "endpoints": [],
                "flags": [],
            },
        },
        # ================= SUPPORT =================
        "Support & Offboarding": {
            "SLA Support / Resolution": {
                "endpoints": [],
                "flags": [],
            },
            "Offboarding Support": {
                "endpoints": [],
                "flags": [],
            },
        },
    },
    Platform.CONSOLE: {
        "User Management": {
            "Manage Users": {
                "endpoints": [
                    "get_all_users",
                    "delete_user",
                    "update_user",
                    "get_users_by_partner_id",
                    "get_user_by_user_id",
                    "get_admin_details_by_partner_id",
                    "enlist_users_dynamically",
                ],
                "flags": [],
            },
        },
    },
    Platform.BABBLER: {
        "Multi Number Support": {
            "endpoints": [
                "get_all_numbers",
                "sync_phone_details",
                "delete_phone_number",
                "restore_phone_number",
            ],
            "flags": [],
        },
        "Inbox": {
            "Chat": {
                "endpoints": [
                    "chat_history",
                    "whatsapp_history",
                    "get_active_contact",
                    "send_message",
                ],
                "flags": [],
            },
            "Dispositions": {
                "endpoints": [
                    "get_all_disposition",
                    "create_disposition",
                    "update_disposition",
                    "delete_disposition",
                    "map_contact_disposition",
                ],
                "flags": [],
            },
            "Labels": {
                "endpoints": [
                    "get_label_by_id",
                    "get_all_labels",
                    "add_label",
                    "update_label",
                    "delete_label",
                    "map_labels_to_contact",
                    "unmap_labels",
                ],
                "flags": [],
            },
            "Filters": {
                "endpoints": [],
                "flags": [],
            },
            "Add Contact": {
                "endpoints": [
                    "create_contact",
                ],
                "flags": [],
            },
            "Chat Assignment": {
                "endpoints": [
                    "chat_assigned",
                ],
                "flags": [],
            },
        },

        "Contact": {
            "Add Contact": {
                "endpoints": [
                    "create_contact",
                ],
                "flags": [],
            },
            "Custom Fields": {
                "endpoints": [
                    "add_custom_field",
                    "delete_custom_field",
                ],
                "flags": [],
            },
        },

        "Audience": {
            "Create Audience": {
                "endpoints": [
                    "map_audience",
                ],
                "flags": [],
            },
            "Bulk Upload / Manual Entry": {
                "endpoints": [],
                "flags": [],
            },
            "Upload History": {
                "endpoints": [],
                "flags": [],
            },
        },

        "Campaign": {
            "Create Campaign": {
                "endpoints": [
                    "create_campaign",
                    "get_campaign",
                    "get_campaign_detail",
                    "campaign_detail_by_phone_no_id",
                ],
                "flags": [],
            },
            "Campaign Scheduler": {
                "endpoints": [
                    "campaign_sync",
                ],
                "flags": [],
            },
            "Campaign Report": {
                "endpoints": [
                    "get_campaign_report",
                ],
                "flags": [],
            },
            "Bulk Upload": {
                "endpoints": [],
                "flags": [],
            },
            "Upload History": {
                "endpoints": [],
                "flags": [],
            },
        },

        "Template": {
            "Standard Template": {
                "endpoints": [
                    "add_template",
                    "get_all_template",
                    "get_template",
                    "update_template",
                    "delete_template",
                ],
                "flags": [],
            },
            "Carousel": {
                "endpoints": [],
                "flags": [],
            },
            "WhatsApp Flow Template": {
                "endpoints": [],
                "flags": [],
            },
            "Sync with Meta": {
                "endpoints": [
                    "sync_templates",
                    "get_templates_shared",
                ],
                "flags": [],
            },
            "Send Template": {
                "endpoints": [
                    "send_template",
                ],
                "flags": [],
            },
        },

        "Management": {
            "Phone Number (Business Profile)": {
                "endpoints": [
                    "update_business_profile",
                    "get_business_profile",
                    "subscribe_waba_app",
                ],
                "flags": [],
            },
            "Users": {
                "endpoints": [
                    "get_user_config",
                    "get_mapped_users",
                    "map_user",
                    "unmap_user_phone",
                ],
                "flags": [],
            },
            "Audience Mapping": {
                "endpoints": [
                    "map_audience",
                    "unmap_users_audience",
                ],
                "flags": [],
            },
            "Labels Configuration": {
                "endpoints": [
                    "add_label",
                    "delete_label",
                ],
                "flags": [],
            },
            "Dispositions Configuration": {
                "endpoints": [
                    "create_disposition",
                    "delete_disposition",
                ],
                "flags": [],
            }
        },

        "WhatsApp Flow": {
            "Create Flow": {
                "endpoints": [],
                "flags": [],
            },
            "Flow Template": {
                "endpoints": [],
                "flags": [],
            },
            "Inbox Flow Preview": {
                "endpoints": [],
                "flags": [],
            },
            "Download CSV Responses": {
                "endpoints": [],
                "flags": [],
            },
        },

        "Automation": {
            "Create Chatbot (Workflows)": {
                "endpoints": [
                    "create_bot",
                    "get_all_bots",
                    "get_bot_details",
                    "update_bot",
                    "delete_bot",
                ],
                "flags": [],
            },
            "Bot Timer": {
                "endpoints": [
                    "add_bot_timer",
                    "get_bot_timer",
                    "update_bot_timer",
                ],
                "flags": [],
            },
            "Triggers": {
                "endpoints": [],
                "flags": [],
            },
        },

        "CTWA": {
            "Integration (Maglo Lead Auto Creation)": {
                "endpoints": [
                    "get_internal_service_config",
                    "add_internal_service_config",
                ],
                "flags": [],
            },
        },
    },
}
