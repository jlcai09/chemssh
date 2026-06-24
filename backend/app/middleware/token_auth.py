from __future__ import annotations

import hmac
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.core.config import Settings
from backend.app.core.errors import error_payload


AUTH_COOKIE_NAME = "chemssh_token"
AUTH_QUERY_NAMES = ("token", "access_token")


class TokenAuthMiddleware:
    def __init__(self, app: ASGIApp, *, settings: Settings, api_prefix: str = "/api") -> None:
        self.app = app
        self.settings = settings
        self.api_prefix = api_prefix.rstrip("/") or "/api"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._should_check(scope):
            await self.app(scope, receive, send)
            return

        valid, source = self._valid_token(scope)
        if not valid:
            await self._reject(scope, receive, send)
            return

        if scope["type"] == "http" and source != "cookie":
            await self.app(scope, receive, self._with_auth_cookie(scope, send))
            return

        await self.app(scope, receive, send)

    def _should_check(self, scope: Scope) -> bool:
        if scope["type"] not in {"http", "websocket"}:
            return False
        if not self.settings.security.enable_token:
            return False
        if scope["type"] == "http" and scope.get("method") == "OPTIONS":
            return False
        path = str(scope.get("path") or "")
        return path == self.api_prefix or path.startswith(f"{self.api_prefix}/")

    def _valid_token(self, scope: Scope) -> tuple[bool, str | None]:
        expected = self.settings.security.token
        if not expected:
            return False, None

        for source, token in self._candidate_tokens(scope):
            if token and self._constant_time_equal(token, expected):
                return True, source
        return False, None

    @staticmethod
    def _constant_time_equal(left: str, right: str) -> bool:
        return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))

    def _candidate_tokens(self, scope: Scope) -> list[tuple[str, str | None]]:
        headers = Headers(scope=scope)
        candidates: list[tuple[str, str | None]] = [
            ("authorization", self._bearer_token(headers.get("authorization"))),
            ("header", headers.get("x-chemssh-token")),
        ]

        query = parse_qs(scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
        for name in AUTH_QUERY_NAMES:
            values = query.get(name)
            if values:
                candidates.append(("query", values[-1]))

        cookie_header = headers.get("cookie")
        if cookie_header:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            morsel = cookie.get(AUTH_COOKIE_NAME)
            if morsel is not None:
                candidates.append(("cookie", morsel.value))

        return candidates

    @staticmethod
    def _bearer_token(value: str | None) -> str | None:
        if not value:
            return None
        scheme, _, token = value.strip().partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return token

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": "Invalid or missing ChemSSH token"})
            return

        headers: dict[str, str] = {"WWW-Authenticate": "Bearer"}
        # Add CORS headers so cross-origin clients can read the 401 response.
        # TokenAuth runs inside CORSMiddleware, so _reject bypasses it;
        # we must add the headers ourselves.
        origin = Headers(scope=scope).get("origin")
        if origin and origin in self.settings.server.cors_origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
            headers["Vary"] = "Origin"

        response = JSONResponse(
            status_code=401,
            content=error_payload("AUTH_REQUIRED", "Invalid or missing ChemSSH token"),
            headers=headers,
        )
        await response(scope, receive, send)

    def _with_auth_cookie(self, scope: Scope, send: Send) -> Send:
        cookie = self._auth_cookie_header(scope)

        async def send_with_cookie(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("set-cookie", cookie)
            await send(message)

        return send_with_cookie

    def _auth_cookie_header(self, scope: Scope) -> str:
        response = Response()
        # Use 'lax' for cross-origin development environments (different ports)
        # In production with HTTPS, this still provides good security
        samesite = "lax" if scope.get("scheme") == "http" else "strict"
        response.set_cookie(
            AUTH_COOKIE_NAME,
            self.settings.security.token,
            httponly=True,
            secure=scope.get("scheme") == "https",
            samesite=samesite,
            path=self.api_prefix,
        )
        for name, value in response.raw_headers:
            if name.lower() == b"set-cookie":
                return value.decode("latin-1")
        raise RuntimeError("Could not build auth cookie")
