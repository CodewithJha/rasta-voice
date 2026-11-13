"""Response policy outside the error stack, including unhandled HTTP errors."""

from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rasta.http_counts import HttpCountMiddleware
from rasta.origins import request_http_scheme
from rasta.request_id import RequestIdApp
from rasta.settings import get_settings

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "media-src 'self' blob:",
        "worker-src 'self' blob:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    )
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeaders:
    """Keep policy headers on normal responses, middleware denials and 500s."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        use_hsts = settings.is_production or request_http_scheme(scope, settings) == "https"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Do not mutate a response object shared by another request.
                message = {**message, "headers": list(message.get("headers", []))}
                headers = MutableHeaders(scope=message)
                for key, value in SECURITY_HEADERS.items():
                    headers[key] = value
                if use_hsts:
                    headers["Strict-Transport-Security"] = HSTS
            await send(message)

        await self.app(scope, receive, send_with_headers)


class SecuredApp(RequestIdApp):
    """Request IDs enclose headers, which enclose FastAPI's full error stack."""

    def build_middleware_stack(self) -> ASGIApp:
        return SecurityHeaders(HttpCountMiddleware(self.build_response_stack()))

    def build_response_stack(self) -> ASGIApp:
        return self.build_perimeter(self.build_application_stack())

    def build_perimeter(self, app: ASGIApp) -> ASGIApp:
        """Host and CORS checks must run before any replay or charged work."""
        settings = get_settings()
        app = CORSMiddleware(
            app,
            allow_origins=list(settings.cors_allow_origins),
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )
        if settings.allowed_hosts:
            app = TrustedHostMiddleware(app, allowed_hosts=list(settings.allowed_hosts))
        return app

    def build_application_stack(self) -> ASGIApp:
        """Build FastAPI handlers and inner admission limits."""
        return super().build_middleware_stack()
