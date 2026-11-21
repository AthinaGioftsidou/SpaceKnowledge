"""The admin routes of the DMZ. They translate HTTP into AdminService calls and
back, and decide nothing themselves."""

from collections.abc import Callable
from typing import Any

from spaceknowledge.app.admin_service import AdminService
from spaceknowledge.common.refusal import Refusal
from spaceknowledge.dmz.http_protocol import (
    MAX_NAME,
    HttpProblem,
    bearer_token,
    only_fields,
    text_field,
)

Reply = tuple[int, dict[str, Any]]
Authorization = str | None
MAX_CODE = 64


class AdminRoutes:
    """Path to handler. A handler gets the parsed body and the Authorization
    header. The token is ALWAYS looked up in the admin sessions, so a customer
    token can never pass here."""

    def __init__(self, admin: AdminService) -> None:
        if not isinstance(admin, AdminService):
            raise TypeError(f"admin must be an AdminService, not {type(admin).__name__}")
        self._admin = admin

    def table(self) -> dict[str, Callable[[dict[str, Any], Authorization], Reply]]:
        return {
            "/admin/code": self.code,
            "/admin/login": self.login,
            "/admin/logout": self.logout,
            "/admin/players": self.players,
            "/admin/stats": self.stats,
        }

    def code(self, body: dict[str, Any], authorization: Authorization) -> Reply:
        only_fields(body, {"admin"})
        self._admin.request_code(text_field(body, "admin", MAX_NAME))
        # The same answer for every name, so it cannot be used to find admins.
        return 202, {"ok": True}

    def login(self, body: dict[str, Any], authorization: Authorization) -> Reply:
        only_fields(body, {"admin", "code"})
        result = self._admin.login(
            text_field(body, "admin", MAX_NAME), text_field(body, "code", MAX_CODE))
        if isinstance(result, Refusal):
            raise HttpProblem(401, result)
        return 200, {"ok": True, "token": result}

    def logout(self, body: dict[str, Any], authorization: Authorization) -> Reply:
        token = bearer_token(authorization)
        only_fields(body, set())
        return 200, {"ok": True, "was_logged_in": self._admin.logout(token)}

    def players(self, body: dict[str, Any], authorization: Authorization) -> Reply:
        token = bearer_token(authorization)
        only_fields(body, set())
        result = self._admin.players(token)
        if isinstance(result, Refusal):
            raise HttpProblem(401, result)
        return 200, {"ok": True, "players": result}

    def stats(self, body: dict[str, Any], authorization: Authorization) -> Reply:
        token = bearer_token(authorization)
        only_fields(body, set())
        result = self._admin.stats(token)
        if isinstance(result, Refusal):
            raise HttpProblem(401, result)
        return 200, {"ok": True, "stats": result}