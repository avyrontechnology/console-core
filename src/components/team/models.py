import uuid
from sqlalchemy import Boolean, Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from src.components.database.base_model import MetaData


class Team(MetaData):
    """
    A partner-scoped, nestable group of users.

    Teams add an organizational + data-scoping dimension on top of the existing
    role hierarchy and reporting (``parent_id``) tree. A user can belong to many
    teams (see :class:`TeamMember`). ``is_internal`` is inherited from the
    partner so internal and external teams never mix.
    """

    __tablename__ = "console_team"

    name = Column(String(128), nullable=False)
    slug = Column(String(128), nullable=False)
    partner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_partners.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    parent_team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_team.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    is_internal = Column(Boolean, default=False, index=True)
    is_active = Column(Boolean, default=True, index=True)
    is_deleted = Column(Boolean, default=False, index=True)

    # Self-referential nesting (Vertical -> Team -> sub-team).
    parent = relationship("Team", remote_side="Team.id", backref="sub_teams")
    members = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("partner_id", "slug", name="uq_team_partner_slug"),
    )

    def __repr__(self) -> str:
        return (
            f"<Team(id={self.id}, name={self.name!r}, partner_id={self.partner_id}, "
            f"parent_team_id={self.parent_team_id})>"
        )


class TeamMember(MetaData):
    """
    Membership of a user in a team (many-to-many).

    ``role_id`` is an optional *per-team role override*: when set, it overrides
    the user's default ``User.role_id`` while acting in this team; when ``NULL``
    the user's default role applies (today's behavior).
    """

    __tablename__ = "console_team_member"

    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_team.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_role.id", ondelete="RESTRICT"),
        nullable=True,
    )

    team = relationship("Team", back_populates="members")

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member_team_user"),
    )

    def __repr__(self) -> str:
        return (
            f"<TeamMember(team_id={self.team_id}, user_id={self.user_id}, "
            f"role_id={self.role_id})>"
        )
