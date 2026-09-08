"""Test helpers: a wait loop and small accessors shared by the UI tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from bjorn.app import BjornApp
from bjorn.bear import BearClient
from bjorn.config import Config

FAKE = Path(__file__).resolve().parents[1] / "src" / "bjorn" / "fake_bearcli.py"
FAKE_REMCTL = Path(__file__).resolve().parents[1] / "src" / "bjorn" / "fake_remctl.py"


@pytest.fixture
def fake_state(tmp_path, monkeypatch) -> Path:
    """Point the fake at a per-test state file. It seeds itself on first use."""
    state = tmp_path / "bear.json"
    monkeypatch.setenv("BJORN_FAKE_BEAR_STATE", str(state))
    monkeypatch.delenv("BJORN_BEARCLI", raising=False)
    return state


@pytest.fixture
def client(fake_state) -> BearClient:
    return BearClient([sys.executable, str(FAKE)])


@pytest.fixture
def remctl_state(tmp_path, monkeypatch) -> Path:
    state = tmp_path / "reminders.json"
    monkeypatch.setenv("BJORN_FAKE_REMCTL_STATE", str(state))
    monkeypatch.delenv("BJORN_REMCTL", raising=False)
    return state


@pytest.fixture
def remctl(remctl_state):
    from bjorn.reminders import RemctlClient

    return RemctlClient([sys.executable, str(FAKE_REMCTL)])


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(poll_seconds=0, export_dir=tmp_path / "exports")


@pytest.fixture
def make_app(client, config):
    def factory(**kwargs) -> BjornApp:
        kwargs.setdefault("client", client)
        kwargs.setdefault("environ", {})
        return BjornApp(config, **kwargs)

    return factory
