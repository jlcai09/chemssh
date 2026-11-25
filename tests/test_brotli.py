from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy

import brotli
import pytest
from starlette.datastructures import Headers
from starlette.types import Message, Receive, Scope, Send

from backend.app.middleware.brotli import BrotliMiddleware


def run_response(
    messages: list[Message],
    check_step: Callable[[int, list[Message]], None],
    *,
    enabled: bool = True,
    method: str = "GET",
    accept_encoding: str = "br",
) -> list[Message]:
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        for index, message in enumerate(messages):
            await send(message)
            check_step(index, sent)

    async def receive() -> Message:
        raise AssertionError("The middleware must not read the request body")

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": method,
        "headers": [(b"accept-encoding", accept_encoding.encode("ascii"))],
    }
    asyncio.run(BrotliMiddleware(app, enabled=enabled)(scope, receive, send))
    return sent


@pytest.mark.parametrize(
    ("status", "headers"),
    [
        pytest.param(200, [(b"content-type", b"application/zip")], id="zip"),
        pytest.param(200, [(b"content-type", b"application/octet-stream")], id="binary"),
        pytest.param(200, [(b"content-type", b"image/png")], id="image"),
        pytest.param(200, [], id="no-content-type"),
        pytest.param(204, [(b"content-type", b"application/json")], id="204"),
        pytest.param(206, [(b"content-type", b"text/plain")], id="206"),
        pytest.param(206, [(b"content-type", b"text/event-stream")], id="206-sse"),
        pytest.param(304, [(b"content-type", b"application/json")], id="304"),
        pytest.param(
            200, [(b"content-type", b"application/json"), (b"content-encoding", b"gzip")], id="gzip"
        ),
        pytest.param(
            200, [(b"content-type", b"text/event-stream"), (b"content-encoding", b"br")], id="encoded-sse"
        ),
        pytest.param(
            200, [(b"content-type", b"application/json"), (b"content-encoding", b"identity")], id="identity"
        ),
        pytest.param(
            200, [(b"content-type", b"application/json"), (b"content-encoding", b"")], id="empty-encoding"
        ),
    ],
)
def test_ineligible_responses_pass_through_every_message_immediately(
    status: int, headers: list[tuple[bytes, bytes]]
) -> None:
    chunks = [b"first chunk", b"", b"second chunk", b""] if status not in {204, 304} else [b""]
    response_headers = headers + [(b"vary", b"Origin")]
    if status != 204:
        response_headers.append((b"content-length", str(sum(map(len, chunks))).encode("ascii")))
    if status == 206:
        response_headers.append((b"content-range", b"bytes 0-22/100"))
    messages: list[Message] = [
        {"type": "http.response.start", "status": status, "headers": response_headers},
        *[
            {"type": "http.response.body", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ],
    ]
    expected = deepcopy(messages)

    def check_step(index: int, sent: list[Message]) -> None:
        assert len(sent) == index + 1
        assert sent[-1] is messages[index]
        assert sent == expected[: index + 1]

    run_response(messages, check_step)


def test_file_send_extension_preserves_uncompressed_headers() -> None:
    messages: list[Message] = [
        {"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain"), (b"content-length", b"20")]},
        {"type": "http.response.pathsend", "path": "fixture.txt"},
    ]
    expected = deepcopy(messages)

    def check_step(index: int, sent: list[Message]) -> None:
        assert sent == ([] if index == 0 else expected)

    run_response(messages, check_step)


@pytest.mark.parametrize("content_type", [b"application/json", b"text/event-stream"])
@pytest.mark.parametrize(
    ("enabled", "method", "accept_encoding"),
    [
        pytest.param(False, "GET", "br", id="disabled"),
        pytest.param(True, "HEAD", "br", id="head"),
        pytest.param(True, "GET", "br;q=0", id="q-zero"),
        pytest.param(True, "GET", "br;q=0, *;q=1", id="q-zero-overrides-wildcard"),
        pytest.param(True, "GET", "*;q=0", id="wildcard-zero"),
        pytest.param(True, "GET", "br;q=invalid, *;q=1", id="invalid-q"),
        pytest.param(True, "GET", "gzip", id="no-br"),
        pytest.param(True, "GET", "", id="no-accept-encoding"),
    ],
)
def test_request_bypasses_preserve_send_order_and_headers(
    content_type: bytes, enabled: bool, method: str, accept_encoding: str
) -> None:
    messages: list[Message] = [
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", content_type), (b"content-length", b"6"), (b"vary", b"Origin")],
        },
        {"type": "http.response.body", "body": b"one", "more_body": True},
        {"type": "http.response.body", "body": b"two"},
    ]
    expected = deepcopy(messages)

    def check_step(index: int, sent: list[Message]) -> None:
        assert len(sent) == index + 1
        assert sent[-1] is messages[index]
        assert sent == expected[: index + 1]

    run_response(messages, check_step, enabled=enabled, method=method, accept_encoding=accept_encoding)


@pytest.mark.parametrize("with_length", [False, True])
@pytest.mark.parametrize(
    "body_message",
    [{"type": "http.response.body"}, {"type": "http.response.body", "body": b"", "more_body": False}],
)
def test_empty_single_body_is_not_compressed(with_length: bool, body_message: Message) -> None:
    headers = [(b"content-type", b"application/json"), (b"vary", b"Origin")]
    if with_length:
        headers.append((b"content-length", b"0"))
    messages: list[Message] = [{"type": "http.response.start", "status": 200, "headers": headers}, body_message]
    expected = deepcopy(messages)

    def check_step(index: int, sent: list[Message]) -> None:
        assert sent == ([] if index == 0 else expected)

    run_response(messages, check_step)


@pytest.mark.parametrize("with_length", [False, True])
@pytest.mark.parametrize("accept_encoding", ["br", "gzip, BR; q=0.5", "*;q=1"])
@pytest.mark.parametrize(
    ("vary", "expected_vary"),
    [
        (None, "Accept-Encoding"),
        (b"Origin", "Origin, Accept-Encoding"),
        (b"Origin, aCcEpT-EnCoDiNg", "Origin, aCcEpT-EnCoDiNg"),
        (b"*", "*"),
        (b"Origin, *", "Origin, *"),
    ],
)
def test_single_json_has_compressed_length_and_preserves_vary(
    with_length: bool, accept_encoding: str, vary: bytes | None, expected_vary: str
) -> None:
    body = b'{"items":[1,2,3],"message":"single response"}'
    headers = [(b"content-type", b"application/json; charset=utf-8")]
    if with_length:
        headers.append((b"content-length", str(len(body)).encode("ascii")))
    if vary is not None:
        headers.append((b"vary", vary))
    messages: list[Message] = [
        {"type": "http.response.start", "status": 200, "headers": headers},
        {"type": "http.response.body", "body": body},
    ]

    def check_step(index: int, sent: list[Message]) -> None:
        if index == 0:
            assert sent == []
            return
        assert [message["type"] for message in sent] == ["http.response.start", "http.response.body"]
        response_headers = Headers(raw=sent[0]["headers"])
        assert response_headers["content-type"] == "application/json; charset=utf-8"
        assert response_headers["content-encoding"] == "br"
        assert response_headers["content-length"] == str(len(sent[1]["body"]))
        assert response_headers["vary"] == expected_vary
        assert not sent[1].get("more_body", False)
        assert brotli.decompress(sent[1]["body"]) == body

    run_response(messages, check_step, accept_encoding=accept_encoding)


@pytest.mark.parametrize(
    "content_type",
    [b"text/plain; charset=utf-8", b"application/javascript", b"text/event-stream; charset=utf-8"],
)
@pytest.mark.parametrize("with_length", [False, True])
@pytest.mark.parametrize(
    "chunks",
    [
        pytest.param([b"data: first\n\n", b"data: second\n\n"], id="nonempty-final"),
        pytest.param([b"data: first\n\n", b"", b"data: second\n\n", b""], id="empty-final"),
        pytest.param([b"", b"data: second\n\n", b""], id="empty-first"),
        pytest.param([b"", b""], id="empty-stream"),
    ],
)
def test_streams_deliver_each_chunk_before_next_send(
    content_type: bytes, with_length: bool, chunks: list[bytes]
) -> None:
    headers = [(b"content-type", content_type), (b"vary", b"Origin")]
    if with_length:
        headers.append((b"content-length", str(sum(map(len, chunks))).encode("ascii")))
    messages: list[Message] = [
        {"type": "http.response.start", "status": 200, "headers": headers},
        *[
            {"type": "http.response.body", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ],
    ]
    decoder = brotli.Decompressor()

    def check_step(index: int, sent: list[Message]) -> None:
        if index == 0:
            assert len(sent) == (1 if content_type.startswith(b"text/event-stream") else 0)
            if not sent:
                return
        else:
            assert len(sent) == index + 1
            outgoing = sent[-1]
            assert outgoing["type"] == "http.response.body"
            assert outgoing["more_body"] == messages[index]["more_body"]
            assert decoder.process(outgoing["body"]) == messages[index]["body"]
            assert decoder.is_finished() == (not messages[index]["more_body"])
        assert sent[0]["type"] == "http.response.start"
        response_headers = Headers(raw=sent[0]["headers"])
        assert response_headers["content-type"] == content_type.decode("ascii")
        assert response_headers["content-encoding"] == "br"
        assert "content-length" not in response_headers
        assert response_headers["vary"] == "Origin, Accept-Encoding"

    sent = run_response(messages, check_step)
    assert brotli.decompress(b"".join(message["body"] for message in sent[1:])) == b"".join(chunks)


def test_empty_sse_sends_headers_immediately_and_finishes_stream() -> None:
    messages: list[Message] = [
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/event-stream"), (b"content-length", b"0")],
        },
        {"type": "http.response.body"},
    ]

    def check_step(index: int, sent: list[Message]) -> None:
        assert len(sent) == index + 1
        headers = Headers(raw=sent[0]["headers"])
        assert headers["content-encoding"] == "br"
        assert "content-length" not in headers
        if index == 1:
            assert not sent[1].get("more_body", False)
            assert brotli.decompress(sent[1]["body"]) == b""

    run_response(messages, check_step)


def test_many_chunks_reuse_one_compressor_without_one_shot_compression(monkeypatch: pytest.MonkeyPatch) -> None:
    compressed_chunks: list[bytes] = []
    created = 0
    delivered = 0
    started = False
    chunk_count = 128

    def make_compressor(*, quality: int) -> brotli.Compressor:
        nonlocal created
        created += 1
        assert quality == 4
        return brotli.Compressor(quality=quality)

    def fail_compress(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("Streaming responses must not use one-shot compression")

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain"), (b"content-length", b"8388608")],
        })
        for index in range(chunk_count):
            await send({
                "type": "http.response.body",
                "body": index.to_bytes(4, "little") * 16384,
                "more_body": index < chunk_count - 1,
            })
            assert delivered == index + 1

    async def receive() -> Message:
        raise AssertionError("The middleware must not read the request body")

    async def send(message: Message) -> None:
        nonlocal delivered, started
        if message["type"] == "http.response.start":
            assert not started
            started = True
            headers = Headers(raw=message["headers"])
            assert headers["content-encoding"] == "br"
            assert "content-length" not in headers
            return
        assert started
        assert message["body"]
        compressed_chunks.append(message["body"])
        delivered += 1
        assert message["more_body"] == (delivered < chunk_count)

    middleware = BrotliMiddleware(app, quality=4)
    monkeypatch.setattr(middleware, "compress", fail_compress)
    monkeypatch.setattr(middleware, "compressor_factory", make_compressor)
    scope: Scope = {"type": "http", "method": "GET", "headers": [(b"accept-encoding", b"br")]}
    asyncio.run(middleware(scope, receive, send))
    assert created == 1
    assert delivered == chunk_count
    assert brotli.decompress(b"".join(compressed_chunks)) == b"".join(
        index.to_bytes(4, "little") * 16384 for index in range(chunk_count)
    )
