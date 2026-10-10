from datetime import datetime

from sqlalchemy import String, cast, func, literal_column
from sqlalchemy.future import select
from sqlalchemy.orm import Query, aliased
from sqlalchemy.sql import exists

from src.components.common.datetime import DateTimeUtil
from src.components.filters.builder import BaseFilterBuilder
from src.components.filters.criteria import BaseFilterCriteria
from src.components.partner.models import Partner
from src.components.partner_config.models import PartnerConfig
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.user.models import User
from src.exceptions import PartnerException


class PartnerFilterBuilder(BaseFilterBuilder):

    def __init__(self, criteria: BaseFilterCriteria, base_query: Query):
        # Pass both User and Role models to the base class
        super().__init__([Partner], criteria, base_query)

    def handle_custom_filter(self, query, field_name, value):
        """Handle non-Partner fields like admin email / phone number."""
        if field_name in {"email", "phone_number"}:
            admin_alias = aliased(User)
            field = (
                admin_alias.email if field_name == "email" else admin_alias.phone_number
            )
            ilike_value = (
                f"%{value.lower()}%" if field_name == "email" else f"%{value}%"
            )

            subquery = (
                select(admin_alias)
                .where(
                    admin_alias.partner_id == Partner.id,
                    (
                        func.lower(field).ilike(ilike_value)
                        if field_name == "email"
                        else field.ilike(ilike_value)
                    ),
                )
                .exists()
            )
            return query.where(subquery)

        if field_name == "is_partner_paid":
            paid_alaias = aliased(PartnerConfig)
            subquery = (
                select(literal_column("1"))
                .where(
                    paid_alaias.partner_id == Partner.id,
                    paid_alaias.key == "is_maglo_enabled",
                    cast(paid_alaias.value, String) == "true",
                )
                .exists()
            )
            return query.where(subquery if value else ~subquery)

        if field_name == "is_free_trial_enabled":
            meta_alias = aliased(PartnerMetaData)
            current_time_ms = DateTimeUtil.get_current_time()
            subquery = (
                select(literal_column("1"))
                .where(
                    meta_alias.partner_id == Partner.id,
                    meta_alias.maglo_trail_expiry_time != None,
                    meta_alias.maglo_trail_expiry_time > current_time_ms,
                )
                .exists()
            )
            return query.where(subquery if value else ~subquery)
        return None

    def _resolve_field_from_models(self, field_name: str):
        if not hasattr(Partner, field_name):
            raise PartnerException(
                "Field '{}' does not exist in Partner model".format(field_name)
            )
        return getattr(Partner, field_name)
