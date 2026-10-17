"""``GET /api/v1/forge/guild``: the Guild this Forge node belongs to.

A node's own notification feed is node-only. A client that registered the node
directly reads this to find the Guild whose facade merges every member's feed,
and the instance id the Guild keys this node's items and read state by.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from niuu.domain.guild_membership import GuildMembership
from volundr.adapters.inbound.auth import extract_principal
from volundr.domain.models import Principal

NOT_JOINED_DETAIL = "This Forge node is not joined to a Guild"


class GuildMembershipResponse(BaseModel):
    guild_url: str
    instance_id: str | None
    instance_name: str | None
    instance_slug: str | None


def create_guild_router(
    membership: GuildMembership | None,
    *,
    prefix: str = "/api/v1/forge",
) -> APIRouter:
    """Serve this node's Guild membership; 404 when it belongs to no Guild."""
    router = APIRouter(prefix=prefix, tags=["Guild"])

    @router.get(
        "/guild",
        response_model=GuildMembershipResponse,
        responses={404: {"description": NOT_JOINED_DETAIL}},
    )
    async def get_guild(
        _principal: Principal = Depends(extract_principal),
    ) -> GuildMembershipResponse:
        if membership is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_JOINED_DETAIL)
        return GuildMembershipResponse(**membership.wire())

    return router
