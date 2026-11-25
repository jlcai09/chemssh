from __future__ import annotations

from collections.abc import Callable
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


Compress = Callable[..., bytes]
CompressorFactory = Callable[..., Any]
COMPRESSIBLE_TYPES = {
    "application/json",
    "application/javascript",
    "application/xml",
    "application/xhtml+xml",
    "image/svg+xml",
    "application/vnd.chemssh.structure+bin",
}
STREAMING_TYPES = {
    "text/event-stream",
}


class BrotliMiddleware:
    def __init__(self, app: ASGIApp, *, enabled: bool = True, quality: int = 1) -> None:
        self.app = app
        self.enabled = enabled
        self.quality = quality
        self.compress: Compress | None = None
        self.compressor_factory: CompressorFactory | None = None

        if enabled:
            try:
                import brotli
            except ImportError as exc:  # pragma: no cover - depends on install state
                raise RuntimeError("Brotli compression is enabled but the 'Brotli' package is not installed.") from exc
            self.compress = brotli.compress
            self.compressor_factory = brotli.Compressor

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.enabled or self.compress is None or self.compressor_factory is None:
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        if scope.get("method") == "HEAD" or not _accepts_brotli(request_headers.get("accept-encoding", "")):
            await self.app(scope, receive, send)
            return

        responder = _BrotliResponder(self.app, send, self.compress, self.compressor_factory, self.quality)
        await responder(scope, receive)


class _BrotliResponder:
    def __init__(
        self,
        app: ASGIApp,
        send: Send,
        compress: Compress,
        compressor_factory: CompressorFactory,
        quality: int,
    ) -> None:
        self.app = app
        self.send = send
        self.compress = compress
        self.compressor_factory = compressor_factory
        self.quality = quality
        self.initial_message: Message | None = None
        self.passthrough = False
        self.stream_compressor: Any | None = None

    async def __call__(self, scope: Scope, receive: Receive) -> None:
        await self.app(scope, receive, self.send_with_brotli)

    async def send_with_brotli(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = MutableHeaders(raw=list(message["headers"]))
            self.passthrough = not _should_compress(message["status"], headers)
            if self.passthrough:
                await self.send(message)
            elif _should_stream_compress(message["status"], headers):
                await self.start_streaming_response(message)
            else:
                self.initial_message = message
            return

        if self.passthrough or message["type"] != "http.response.body":
            if self.initial_message is not None:
                await self.send(self.initial_message)
                self.initial_message = None
                self.passthrough = True
            await self.send(message)
            return

        if self.stream_compressor is not None:
            await self.send_streaming_body(message)
            return

        if self.initial_message is None:
            await self.send(message)
            return

        if message.get("more_body", False):
            await self.start_streaming_response(self.initial_message)
            await self.send_streaming_body(message)
            return

        await self.send_final_body(message)

    async def start_streaming_response(self, start: Message) -> None:
        self.stream_compressor = self.compressor_factory(quality=self.quality)
        self.initial_message = None
        headers = MutableHeaders(raw=list(start["headers"]))
        headers["Content-Encoding"] = "br"
        if "Content-Length" in headers:
            del headers["Content-Length"]
        _set_vary_accept_encoding(headers)
        start["headers"] = headers.raw
        await self.send(start)

    async def send_streaming_body(self, message: Message) -> None:
        compressor = self.stream_compressor
        if compressor is None:
            await self.send(message)
            return

        body = message.get("body", b"")
        compressed = b""
        if body:
            compressed += compressor.process(body)
            compressed += compressor.flush()
        if not message.get("more_body", False):
            compressed += compressor.finish()

        await self.send({**message, "body": compressed})

    async def send_final_body(self, message: Message) -> None:
        body = message.get("body", b"")
        start = self.initial_message
        self.initial_message = None

        if start is None:
            await self.send(message)
            return

        if not body:
            await self.send(start)
            await self.send(message)
            return

        headers = MutableHeaders(raw=list(start["headers"]))
        compressed = self.compress(body, quality=self.quality)
        headers["Content-Encoding"] = "br"
        headers["Content-Length"] = str(len(compressed))
        _set_vary_accept_encoding(headers)
        start["headers"] = headers.raw

        await self.send(start)
        await self.send({**message, "body": compressed})


def _accepts_brotli(header_value: str) -> bool:
    brotli_q: float | None = None
    wildcard_q: float | None = None

    for part in header_value.split(","):
        encoding, *parameters = part.strip().split(";")
        name = encoding.strip().lower()
        if name not in {"br", "*"}:
            continue

        q = 1.0
        for parameter in parameters:
            key, _, value = parameter.strip().partition("=")
            if key.lower() == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0

        if name == "br":
            brotli_q = q
        else:
            wildcard_q = q

    if brotli_q is not None:
        return brotli_q > 0
    return wildcard_q is not None and wildcard_q > 0


def _should_compress(status_code: int, headers: MutableHeaders) -> bool:
    if status_code < 200 or status_code in {204, 206, 304}:
        return False
    if "Content-Encoding" in headers:
        return False

    content_type = headers.get("Content-Type", "").split(";", 1)[0].lower()
    if not content_type:
        return False

    return (
        content_type.startswith("text/")
        or content_type in COMPRESSIBLE_TYPES
        or content_type.endswith("+json")
        or content_type.endswith("+xml")
    )


def _should_stream_compress(status_code: int, headers: MutableHeaders) -> bool:
    if status_code < 200 or status_code in {204, 206, 304}:
        return False
    if "Content-Encoding" in headers:
        return False
    content_type = headers.get("Content-Type", "").split(";", 1)[0].lower()
    return content_type in STREAMING_TYPES


def _set_vary_accept_encoding(headers: MutableHeaders) -> None:
    current = headers.get("Vary")
    if not current:
        headers["Vary"] = "Accept-Encoding"
        return

    values = [value.strip().lower() for value in current.split(",")]
    if "accept-encoding" not in values and "*" not in values:
        headers["Vary"] = f"{current}, Accept-Encoding"
