"""Smoke tests for scripts/wii_embed.

Loads the script as a module, monkeypatches its `_request` to drive the
FastAPI TestClient directly, then runs each subcommand.
"""

from __future__ import annotations

import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from backend.app.ai import LLMProvider, GenerateResult


pytestmark = pytest.mark.committed_writes


_PATH = Path(__file__).resolve().parent.parent / "scripts" / "wii_embed"


def _load_wii_embed():
    loader = SourceFileLoader("wii_embed", str(_PATH))
    spec = importlib.util.spec_from_loader("wii_embed", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def wii_embed():
    return _load_wii_embed()


@pytest.fixture
def driven(wii_embed, client, monkeypatch):
    """Route the script's HTTP calls through the in-process TestClient."""

    def fake_request(method, path, *, body=None, base_url=None, token=None):
        kwargs = {}
        if body is not None:
            kwargs["json"] = body
        response = client.request(method, path, **kwargs)
        try:
            payload = response.json() if response.content else None
        except json.JSONDecodeError:
            payload = response.text
        return response.status_code, payload

    monkeypatch.setattr(wii_embed, "_request", fake_request)
    return wii_embed


class FakeEmbedProvider(LLMProvider):
    name = "fake"
    embed_model = "fake-embed"

    def __init__(self):
        self.calls = []

    def generate(self, messages, *, system=None):
        return GenerateResult(text="ok")

    def tool_use_loop(self, messages, tools, on_tool_call, *, system=None, max_iterations=8):
        return GenerateResult(text="ok")

    def embed(self, texts):
        self.calls.append(list(texts))
        return [[0.1, 0.2] for _ in texts]


def test_backfill_subcommand(driven, client, monkeypatch, capsys):
    client.post("/nodes", json={"name": "Hammer", "kind": "tool"})
    monkeypatch.setattr(
        "backend.app.routers.embeddings.get_provider", lambda _: FakeEmbedProvider()
    )

    driven.main(["backfill"])

    out = capsys.readouterr().out
    assert "embedded=1" in out
    assert "model=fake-embed" in out


def test_backfill_default_subcommand(driven, client, monkeypatch, capsys):
    """Running `wii_embed` with no subcommand should default to backfill."""
    client.post("/nodes", json={"name": "Drill", "kind": "tool"})
    monkeypatch.setattr(
        "backend.app.routers.embeddings.get_provider", lambda _: FakeEmbedProvider()
    )

    driven.main([])

    out = capsys.readouterr().out
    assert "embedded=1" in out


def test_status_subcommand(driven, client, monkeypatch, capsys):
    client.post("/nodes", json={"name": "Hammer", "kind": "tool"})
    monkeypatch.setattr(
        "backend.app.routers.embeddings.get_provider", lambda _: FakeEmbedProvider()
    )
    driven.main(["backfill"])
    capsys.readouterr()  # drain backfill output

    driven.main(["status"])
    out = capsys.readouterr().out
    assert "fake-embed" in out
    assert "rows=1" in out


def test_status_empty(driven, capsys):
    driven.main(["status"])
    out = capsys.readouterr().out
    assert "no embeddings yet" in out


def test_json_output(driven, client, monkeypatch, capsys):
    client.post("/nodes", json={"name": "Hammer", "kind": "tool"})
    monkeypatch.setattr(
        "backend.app.routers.embeddings.get_provider", lambda _: FakeEmbedProvider()
    )

    driven.main(["--json", "backfill"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["embedded"] == 1
    assert payload["model"] == "fake-embed"
