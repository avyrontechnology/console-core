from uuid import UUID
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select, update, case
from sqlalchemy.dialects.postgresql import ARRAY, INTEGER
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from src.components.auth.constant import UserHierarchyLevel
from src.components.auth.models import Role
from src.components.common.datetime import DateTimeUtil
from src.components.entitlement.models import Entitlement
from src.components.order.constants import MILLISECONDS_IN_DAY, OrderSource, OrderType, PaymentMethod
from src.components.order.errors import OrderNotFoundError
from src.components.order.messages import EXPIRE_ORDER_VIA_CRON
from src.components.order.models import Order
from src.components.order.schema import OrderBase
from src.components.partner.models import Partner
from src.components.partner_address.schema import AddressType
from src.components.payment.enum import PaymentStatusEnum
from src.components.payment.models import Payment
from src.components.plan.models import Plan
from src.components.user.models import User
from src.loggers.console_service_logger import ConsoleServiceLogger


class OrderRepository:
    def __init__(self, session_factory, logger: ConsoleServiceLogger):
        self.session_factory = session_factory
        self.logger = logger

    # =========================================================================
    # SELF-SERVE: INITIATE ORDER
    # =========================================================================

    async def initiate_order(
        self,
        order_data: OrderBase,
        user_id: UUID,
        partner_id: UUID,
        duration: int,
        order_type: str = OrderType.FRESH,
    ) -> Order:
        """
        Persist a self-serve order (payment gateway flow).
        order_type is classified by the service before calling this method.
        payment_method is always GATEWAY for self-serve orders.
        """
        async with self.session_factory() as session:
            try:
                order = Order(
                    partner_id=partner_id,
                    plan_id=order_data.plan_id,
                    add_ons=order_data.add_ons,
                    amount=order_data.amount,
                    currency=order_data.currency,
                    status=PaymentStatusEnum.PENDING,
                    duration=duration,
                    created_by=user_id,
                    source=order_data.source,
                    is_manually_created=False,
                    order_type=order_type,
                    payment_method=PaymentMethod.GATEWAY,
                )
                session.add(order)
                await session.commit()
                await session.refresh(order)
                self.logger.info(
                    "Order initiated | order_id={} order_type={}".format(
                        order.id, order_type
                    )
                )
                return order
            except Exception as e:
                await session.rollback()
                self.logger.error("Error initiating order: {}".format(e))
                raise

    # =========================================================================
    # MANUAL ORDER: CREATE
    # =========================================================================

    async def create_manual_order(
        self,
        partner_id: UUID,
        plan_id: UUID,
        add_ons: dict,
        amount: int,
        currency: str,
        duration_days: int,
        created_by: UUID,
        order_type: str = OrderType.FRESH,
        payment_method: str = PaymentMethod.DIRECT,
        original_order_id: Optional[UUID] = None,
    ) -> Order:
        """
        Persist a manually-created order.

        order_type     : FRESH | RENEWAL | UPGRADE
        payment_method : GATEWAY (provisioned after payment) | DIRECT (provisioned immediately)
        original_order_id is populated for RENEWAL orders only.
        """
        async with self.session_factory() as session:
            try:
                order = Order(
                    partner_id=partner_id,
                    plan_id=plan_id,
                    add_ons=add_ons,
                    amount=amount,
                    currency=currency,
                    status=PaymentStatusEnum.PENDING,
                    duration=duration_days,
                    created_by=created_by,
                    source=OrderSource.CONSOLE,
                    is_manually_created=True,
                    order_type=order_type,
                    payment_method=payment_method,
                    original_order_id=original_order_id,
                )
                session.add(order)
                await session.commit()
                await session.refresh(order)
                self.logger.info(
                    "Manual order created | order_id={} partner_id={} "
                    "order_type={} payment_method={} original_order_id={}".format(
                        order.id,
                        partner_id,
                        order_type,
                        payment_method,
                        original_order_id,
                    )
                )
                return order
            except Exception as e:
                await session.rollback()
                self.logger.error(
                    "Error creating manual order | partner_id={} error={}".format(
                        partner_id, e
                    )
                )
                raise

    # =========================================================================
    # COMMON: UPDATE / FETCH
    # =========================================================================

    async def update_order(
        self, order_id: UUID, update_data: dict, user_id: UUID
    ) -> Order:
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Order).where(Order.id == order_id)
                )
                order = result.scalars().first()

                if not order:
                    raise OrderNotFoundError("Order {} not found".format(order_id))

                for field, value in update_data.items():
                    if hasattr(order, field):
                        setattr(order, field, value)

                order.updated_by = user_id
                await session.commit()
                await session.refresh(order)
                self.logger.info("Order updated: {}".format(order_id))
                return order
            except Exception as e:
                await session.rollback()
                self.logger.error("Error updating order {}: {}".format(order_id, e))
                raise

    async def update_order_if_not_finalized(
        self, order_id: UUID, update_data: dict, user_id: UUID
    ) -> Optional[Order]:
        """
        Atomically finalize an order only if it hasn't already been
        finalized (SUCCESS/REFUNDED) by a concurrent request.

        A plain read-then-write (like ``update_order``) has a race: two
        concurrent ``validate_order`` calls for the same order (double
        click, page refresh, a retry landing at the same moment as an
        earlier one) can both pass the initial status check, both get a
        valid signature from Razorpay, and both write -- double-crediting
        a wallet or creating a duplicate entitlement. The WHERE clause
        below makes the write itself the single source of truth: only the
        request that actually flips the row wins, checked via the DB's own
        atomic UPDATE rather than an application-level lock (which would
        otherwise have to be held across the external Razorpay signature
        check).

        Returns None if another request already finalized the order first
        -- the caller should skip provisioning in that case, since the
        winning request already did it.
        """
        async with self.session_factory() as session:
            try:
                stmt = (
                    update(Order)
                    .where(
                        Order.id == order_id,
                        Order.status.notin_(
                            [PaymentStatusEnum.SUCCESS, PaymentStatusEnum.REFUNDED]
                        ),
                    )
                    .values(**update_data, updated_by=user_id)
                )
                result = await session.execute(stmt)
                await session.commit()

                if not result.rowcount:
                    self.logger.warning(
                        "Order {} was already finalized by a concurrent request; "
                        "skipping.".format(order_id)
                    )
                    return None

                refreshed = await session.execute(
                    select(Order).where(Order.id == order_id)
                )
                order = refreshed.scalars().first()
                self.logger.info("Order updated: {}".format(order_id))
                return order
            except Exception as e:
                await session.rollback()
                self.logger.error("Error updating order {}: {}".format(order_id, e))
                raise

    async def get_order_by_id(self, order_id: UUID) -> Order:
        """
        Fetch a single order by primary key with its plan eagerly loaded.
        Used by manual order renewal to load the original order.
        """
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Order)
                    .options(joinedload(Order.plan))
                    .where(Order.id == order_id)
                )
                order = result.scalars().first()
                if not order:
                    raise OrderNotFoundError("Order {} not found.".format(order_id))
                return order
            except OrderNotFoundError:
                raise
            except Exception as e:
                self.logger.error(
                    "Error fetching order by id={}: {}".format(order_id, e)
                )
                raise

    async def get_latest_order_by_partner(self, partner_id: UUID) -> Optional[Order]:
        """
        Return the most recent SUCCESS order for the partner (by created_at desc),
        with its plan eagerly loaded.

        Used by manual order classification to compare plan hierarchies and
        detect renewals vs upgrades vs downgrades.
        Returns None if the partner has no order history.
        """
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Order)
                    .options(joinedload(Order.plan))
                    .where(
                        Order.partner_id == partner_id,
                        Order.status == PaymentStatusEnum.SUCCESS,
                    )
                    .order_by(Order.created_at.desc())
                    .limit(1)
                )
                return result.scalars().first()
            except Exception as e:
                self.logger.error(
                    "Error fetching latest order | partner_id={} error={}".format(
                        partner_id, e
                    )
                )
                raise

    async def get_order_by_merchant_transaction_id(
        self, merchant_transaction_id: str
    ) -> Order:
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Order).where(
                        Order.merchant_transaction_id == merchant_transaction_id
                    )
                )
                order = result.scalars().first()
                if not order:
                    raise OrderNotFoundError(merchant_transaction_id)
                return order
            except OrderNotFoundError as onfe:
                self.logger.error(
                    f"OrderNotFoundError for '{merchant_transaction_id}': {onfe}"
                )
                raise
            except Exception as e:
                await session.rollback()
                self.logger.error(
                    f"Unexpected error fetching order '{merchant_transaction_id}': {e}"
                )
                raise

    # =========================================================================
    # ORDER HISTORY
    # =========================================================================

    async def get_order_history(
        self,
        filters: Dict[str, Any],
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> tuple[List[Dict], int]:
        async with self.session_factory() as session:
            try:
                conditions: list = self._build_order_conditions(filters)

                base_query = self._build_base_order_query(conditions)
                total_count: int = await self._get_order_count(session, conditions)

                base_query = base_query.order_by(Order.created_at.desc())
                base_query = self._apply_pagination(base_query, limit, offset)

                result = await session.execute(base_query)
                orders = result.unique().scalars().all()

                if not orders:
                    self.logger.info("No orders found with the given filters")
                    return [], 0

                order_data_list: List[Dict] = await self._build_order_data(
                    session, orders
                )

                self.logger.info(
                    f"Fetched {len(order_data_list)} orders (total: {total_count})"
                )

                return order_data_list, total_count

            except Exception as e:
                self.logger.error(f"Error fetching order history: {e}")
                raise

    # ─── Query helpers ────────────────────────────────────────────────────────

    def _build_order_conditions(self, filters: Dict[str, Any]) -> list:
        """
        Build SQLAlchemy filter conditions from the filters dict.

        Supported keys (all optional):
        partner_ids                 : list[UUID]
        source                      : str
        status                      : str
        order_created_at_from       : datetime
        order_created_at_to         : datetime
        entitlement_start_date_from : datetime
        entitlement_start_date_to   : datetime
        entitlement_end_date_from   : datetime
        entitlement_end_date_to     : datetime
        is_manually_created         : bool  ← filters manual vs self-serve
        order_type                  : dict  ← {"op": "eq"|"ne"|"in"|"not_in", "values": [...]}
        """
        conditions: list = []

        if partner_ids := filters.get("partner_ids"):
            conditions.append(Order.partner_id.in_(partner_ids))

        if source := filters.get("source"):
            conditions.append(Order.source == source)

        if status := filters.get("status"):
            conditions.append(Order.status == status)

        if created_from := filters.get("order_created_at_from"):
            conditions.append(Order.created_at >= created_from)

        if created_to := filters.get("order_created_at_to"):
            conditions.append(Order.created_at <= created_to)

        if start_date := filters.get("entitlement_start_date_from"):
            conditions.append(Entitlement.start_date >= start_date)

        if end_date := filters.get("entitlement_start_date_to"):
            conditions.append(Entitlement.start_date <= end_date)

        if start_date := filters.get("entitlement_end_date_from"):
            conditions.append(Entitlement.end_date >= start_date)

        if end_date := filters.get("entitlement_end_date_to"):
            conditions.append(Entitlement.end_date <= end_date)

        # Manual order filters — None means "no filter" (return all)
        if filters.get("is_manually_created") is not None:
            conditions.append(
                Order.is_manually_created.is_(filters["is_manually_created"])
            )

        if order_type_filter := filters.get("order_type"):
            conditions.append(self._build_order_type_condition(order_type_filter))

        return conditions

    def _build_order_type_condition(self, order_type_filter: Dict[str, Any]):
        """Build a single SQLAlchemy condition for the order_type filter dict."""
        _ORDER_TYPE_OPS = {
            "eq": lambda col, v: col == v[0],
            "ne": lambda col, v: col != v[0],
            "in": lambda col, v: col.in_(v),
            "not_in": lambda col, v: col.not_in(v),
        }
        op = order_type_filter.get("op", "eq")
        values = order_type_filter.get("values", [])
        return _ORDER_TYPE_OPS[op](Order.order_type, values)

    def _build_base_order_query(self, conditions: list):
        query = (
            select(Order)
            .options(
                joinedload(Order.partner).joinedload(Partner.addresses),
                joinedload(Order.plan),
                joinedload(Order.payment),
            )
            .join(Partner, Order.partner_id == Partner.id)
            .outerjoin(Plan, Order.plan_id == Plan.id)
            .outerjoin(Payment, Order.id == Payment.order_id)
            .outerjoin(Entitlement, Order.id == Entitlement.order_id)
        )

        if conditions:
            query = query.where(and_(*conditions))

        return query

    async def _get_order_count(self, session, conditions: list) -> int:
        base = (
            select(func.count(func.distinct(Order.id)))
            .select_from(Order)
            .join(Partner, Order.partner_id == Partner.id)
            .outerjoin(Plan, Order.plan_id == Plan.id)
            .outerjoin(Payment, Order.id == Payment.order_id)
            .outerjoin(Entitlement, Order.id == Entitlement.order_id)
        )

        if conditions:
            base = base.where(and_(*conditions))

        result = await session.execute(base)
        return result.scalar() or 0

    def _apply_pagination(self, query, limit: Optional[int], offset: Optional[int]):
        if limit and offset:
            return query.offset((offset - 1) * limit).limit(limit)
        return query

    # ─── Data fetching & mapping ──────────────────────────────────────────────

    async def _build_order_data(self, session, orders: list) -> List[Dict]:
        partner_ids = list({order.partner_id for order in orders})
        order_ids = [order.id for order in orders]

        entitlements = await self._fetch_entitlements(session, order_ids)
        admin_users = await self._fetch_admin_users(session, partner_ids)

        entitlements_by_order = {
            entitlement.order_id: entitlement for entitlement in entitlements
        }
        admin_users_by_partner = {user.partner_id: user for user in admin_users}

        return [
            self._build_single_order_dict(
                order,
                entitlements_by_order.get(order.id),
                admin_users_by_partner.get(order.partner_id),
            )
            for order in orders
        ]

    async def _fetch_entitlements(self, session, order_ids: list):
        query = select(Entitlement).where(
            or_(
                Entitlement.order_id.in_(order_ids),
                Entitlement.additional_info["previous_order_ids"]
                .astext.cast(ARRAY(INTEGER))
                .overlap(order_ids),
            )
        )
        return (await session.execute(query)).scalars().all()

    async def _fetch_admin_users(self, session, partner_ids: list):
        query = (
            select(User)
            .options(
                joinedload(User.country),
                joinedload(User.state),
                joinedload(User.city),
            )
            .join(Role, Role.id == User.role_id)
            .where(
                and_(
                    User.partner_id.in_(partner_ids),
                    Role.hierarchy == UserHierarchyLevel.ADMIN_LEVEL_HIERARCHY,
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                )
            )
        )
        return (await session.execute(query)).unique().scalars().all()

    # ─── Mapping helpers ──────────────────────────────────────────────────────

    def _build_single_order_dict(
        self, order, entitlement, admin_user
    ) -> Dict[str, Any]:
        return {
            "order": self._map_order(order),
            "partner": self._map_partner(order.partner),
            "plan": self._map_plan(order.plan),
            "payment": self._map_payment(order.payment),
            "entitlement": self._map_entitlement(entitlement),
            "admin_user": self._map_admin_user(admin_user),
        }

    def _map_order(self, order) -> Dict[str, Any]:
        return {
            "id": order.id,
            "partner_id": order.partner_id,
            "plan_id": order.plan_id,
            "add_ons": order.add_ons,
            "amount": order.amount,
            "currency": order.currency,
            "status": order.status,
            "merchant_transaction_id": order.merchant_transaction_id,
            "duration": order.duration,
            "source": order.source,
            "created_at": order.created_at,
            "created_by": order.created_by,
            "updated_at": order.updated_at,
            "updated_by": order.updated_by,
            # Manual order fields
            "is_manually_created": getattr(order, "is_manually_created", False),
            "order_type": getattr(order, "order_type", OrderType.FRESH),
            "payment_method": getattr(order, "payment_method", None),
            "original_order_id": getattr(order, "original_order_id", None),
        }

    def _map_partner(self, partner) -> Optional[Dict[str, Any]]:
        if not partner:
            return None

        location = self._get_partner_location(partner.addresses or [])

        return {
            "id": partner.id,
            "name": partner.name,
            "gst_no": partner.gst_no,
            "is_active": partner.is_active,
            "city": location.get("city"),
            "state": location.get("state"),
            "country": location.get("country"),
        }

    def _get_partner_location(self, addresses: list) -> dict:
        """Priority: BILLING → COMMUNICATION_AND_BILLING → COMMUNICATION → empty."""
        for address_type in (
            AddressType.BILLING,
            AddressType.COMMUNICATION_AND_BILLING,
            AddressType.COMMUNICATION,
        ):
            match = next((a for a in addresses if a.address_type == address_type), None)
            if match:
                return {
                    "city": match.city,
                    "state": match.state,
                    "country": match.country,
                }
        return {"city": None, "state": None, "country": None}

    def _map_plan(self, plan) -> Optional[Dict[str, Any]]:
        if not plan:
            return None
        return {
            "id": plan.id,
            "name": plan.name,
            "plan_type": plan.plan_type,
            "duration": plan.duration,
            "price": plan.price,
            "discount_percentage": plan.discount_percentage,
            "limits": plan.limits,
        }

    def _map_payment(self, payment) -> Optional[Dict[str, Any]]:
        if not payment:
            return None
        return {
            "payment_status": payment.payment_status,
            "payment_method": payment.payment_method,
            "created_at": payment.created_at,
        }

    def _map_entitlement(self, entitlement) -> Optional[Dict[str, Any]]:
        if not entitlement:
            return None

        current_time = DateTimeUtil.get_current_time()
        is_active: bool = (
            entitlement.is_active
            and entitlement.end_date is not None
            and entitlement.start_date <= current_time
            and entitlement.end_date >= current_time
        )

        return {
            "start_date": entitlement.start_date,
            "end_date": entitlement.end_date,
            "is_active": is_active,
        }

    def _map_admin_user(self, user) -> Optional[Dict[str, Any]]:
        if not user:
            return None
        return {
            "email": user.email,
            "phone_number": user.phone_number,
            "country": user.country.name if user.country else None,
            "state": user.state.name if user.state else None,
            "city": user.city.name if user.city else None,
        }

    # =========================================================================
    # CRON: EXPIRE PENDING ORDERS
    # =========================================================================

    async def expire_pending_orders_before(self, cutoff: int) -> int:
        """Bulk-expire all PENDING orders created before the cutoff epoch (ms)."""
        async with self.session_factory() as session:
            try:
                stmt = (
                    update(Order)
                    .where(
                        Order.status == PaymentStatusEnum.PENDING,
                        Order.created_at < cutoff,
                    )
                    .values(
                        status=PaymentStatusEnum.FAILED,
                        additional_info={"failed_reason": EXPIRE_ORDER_VIA_CRON},
                    )
                )

                result = await session.execute(stmt)
                await session.commit()

                updated_count = result.rowcount or 0

                if updated_count > 0:
                    self.logger.info(
                        f"Expired {updated_count} pending orders created before {cutoff}"
                    )
                else:
                    self.logger.debug("No pending orders found to expire")

                return updated_count

            except SQLAlchemyError as e:
                await session.rollback()
                self.logger.error(
                    f"Failed to bulk-expire pending orders before {cutoff}: {e}",
                    exc_info=True,
                )
                raise

    async def get_report_for_created_orders(
        self,
        current_ts:int,
        is_manually_created:Optional[bool] = True,
        lookback_days: int = 7,
    ):
        start_ts = current_ts - (
            lookback_days * 24 * 60 * 60 * 1000
        )

        async with self.session_factory() as session:

            columns = [
                Order.partner_id,
                Partner.name.label("partner"),
                Plan.name.label("plan_name"),
                Plan.plan_type.label("plan_type"),
                Order.order_type,
                Order.source.label("order_source"),
                Order.amount,
            ]

            if not is_manually_created:
                columns.extend(
                    [
                        Order.payment_method,
                        Order.status.label("payment_status"),
                    ]
                )

            query = (
                select(*columns)
                .join(Partner, Partner.id == Order.partner_id)
                .outerjoin(Plan, Plan.id == Order.plan_id)
                .where(
                    Order.is_manually_created == is_manually_created,
                    Order.created_at.between(start_ts, current_ts),
                )
                .order_by(Order.partner_id,Order.created_at.desc())
            )

            result = await session.execute(query)

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]
        

    async def get_approaching_renewal_report(
        self,
        current_ts: int,
        renewal_window_days: int = 7,
    ):
        renewal_cutoff_ts = (
            current_ts
            + renewal_window_days * 24 * 60 * 60 * 1000
        )

        async with self.session_factory() as session:

            query = (
                select(
                    Partner.name.label("partner"),
                    Plan.name.label("plan_name"),
                    Plan.plan_type.label("plan_type"),
                    Order.id.label("order_id"),
                    Order.order_type,
                    Order.source.label("order_source"),
                    Order.payment_method,
                    Order.amount,
                    Entitlement.start_date,
                    Entitlement.end_date,
                )
                .join(
                    Order,
                    Order.id == Entitlement.order_id,
                )
                .join(
                    Partner,
                    Partner.id == Entitlement.partner_id,
                )
                .outerjoin(
                    Plan,
                    Plan.id == Order.plan_id,
                )
                .where(
                    Entitlement.is_active.is_(True),
                    Entitlement.end_date.isnot(None),
                    Entitlement.end_date.between(
                        current_ts,
                        renewal_cutoff_ts,
                    ),
                )
                .order_by(
                    Order.partner_id,
                    Entitlement.end_date.asc()
                )
            )

            result = await session.execute(query)

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]
        

    async def get_expired_and_overdue_report(
        self,
        current_ts: int,
        expiry_window_days: int = 7,
    ):
        """
        Returns:
            - EXPIRED : expired within last N days
            - OVERDUE : expired before that window
        """

        window_start = (
            current_ts
            - expiry_window_days * MILLISECONDS_IN_DAY
        )

        async with self.session_factory() as session:

            status_case = case(
                (
                    Entitlement.end_date >= window_start,
                    "EXPIRED",
                ),
                else_="OVERDUE",
            ).label("subscription_status")

            query = (
                select(
                    Partner.name.label("partner"),
                    Plan.name.label("plan_name"),
                    Plan.plan_type.label("plan_type"),
                    Order.id.label("order_id"),
                    Order.order_type,
                    Order.amount,
                    Entitlement.end_date,
                    status_case,
                )
                .join(
                    Order,
                    Order.id == Entitlement.order_id,
                )
                .join(
                    Partner,
                    Partner.id == Entitlement.partner_id,
                )
                .outerjoin(
                    Plan,
                    Plan.id == Order.plan_id,
                )
                .where(
                    Entitlement.end_date.isnot(None),
                    Entitlement.end_date < current_ts,
                )
                .order_by(
                    Order.partner_id,
                    Entitlement.end_date.desc()
                )
            )

            result = await session.execute(query)

            rows = []

            for row in result.fetchall():

                data = dict(row._mapping)

                data["days_since_expiry"] = (
                    current_ts - data["end_date"]
                ) // MILLISECONDS_IN_DAY

                rows.append(data)

            return rows

