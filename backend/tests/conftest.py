"""Shared pytest fixtures.

Why this file exists
---------------------
backend/.env intentionally sets USE_MOCKS=false so the real app and the
live demo hit the real YouCam API. But app.config.Settings reads .env at
import time, which means — without this file — the whole test suite
silently inherits "real API mode" from whatever a developer's local .env
happens to say. That is not hermetic: it makes tests slow (real network
round-trips), potentially expensive (consumes paid API credits from a
fixed 1000-unit budget), and non-reproducible (pass/fail depends on a
git-ignored local file and on network availability).

The fixtures below force every test to start in mock mode with no real
API key, and hard-block any real socket connection for the duration of
the test session. Tests that deliberately exercise real-mode code paths
(test_analyze_body_color.py, test_color.py, test_tryon_route.py,
test_vto.py, test_youcam_client.py) explicitly monkeypatch
`settings.use_mocks = False` themselves and inject an
`httpx.MockTransport`, which never opens a real socket — so they are
unaffected by the network block and continue to opt into real-mode
behaviour deliberately, in-process only.
"""

from __future__ import annotations

import socket

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _force_mock_mode(monkeypatch):
    """Default every test to mock mode with a dummy API key.

    This runs for every test regardless of what backend/.env contains.
    Tests that need real-mode code paths override `use_mocks` (and supply
    an httpx.MockTransport-backed client) themselves, after this fixture
    has already run.
    """
    monkeypatch.setattr(settings, "use_mocks", True)
    monkeypatch.setattr(settings, "youcam_api_key", "sk-test-dummy-key-not-real")


_orig_connect = socket.socket.connect
_orig_create_connection = socket.create_connection


def _is_loopback(address) -> bool:
    if isinstance(address, tuple) and len(address) >= 1:
        host = address[0]
        return str(host) in ("127.0.0.1", "localhost", "::1")
    return False


def _blocked_connect(self, address, *args, **kwargs):
    if _is_loopback(address):
        return _orig_connect(self, address, *args, **kwargs)
    raise RuntimeError(
        "Network access attempted during tests. The test suite must be "
        "hermetic — use httpx.MockTransport (see tests/test_youcam_client.py "
        "for the pattern) instead of making a real outbound call."
    )


def _blocked_create_connection(address, *args, **kwargs):
    if _is_loopback(address):
        return _orig_create_connection(address, *args, **kwargs)
    raise RuntimeError(
        "Network access attempted during tests. The test suite must be "
        "hermetic — use httpx.MockTransport (see tests/test_youcam_client.py "
        "for the pattern) instead of making a real outbound call."
    )


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """Guard fixture: fail loudly if any test attempts a real outbound
    socket connection (e.g. a live call to the YouCam API host).

    httpx.MockTransport never touches a real socket, and FastAPI's
    TestClient talks to the app in-process over an ASGI transport, so
    neither is affected by this block. Anything that *does* try to open a
    real network connection — meaning some code path forgot to inject a
    mock transport — fails immediately and loudly instead of hanging on a
    slow real request or silently spending API credits.
    """
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket, "create_connection", _blocked_create_connection)

