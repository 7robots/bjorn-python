"""Phase 4: config file and editor resolution."""

from __future__ import annotations

from pathlib import Path

from bjorn.config import Config, default_config_path, editor_available, resolve_editor


def test_missing_config_gives_defaults(tmp_path):
    cfg = Config.load(tmp_path / "nope.toml")
    assert cfg.editor == "" and cfg.poll_seconds == 5 and cfg.workspace == ""
    assert cfg.export_dir == Path.home() / "Downloads"


def test_config_values_are_read(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('editor = "nvim"\nexport_dir = "~/exports"\npoll_seconds = 0\nworkspace = "#techne"\nbearcli = "/opt/bearcli"\n')
    cfg = Config.load(path)
    assert cfg.editor == "nvim"
    assert cfg.export_dir == Path("~/exports").expanduser()
    assert cfg.poll_seconds == 0
    assert cfg.workspace == "techne"
    assert cfg.bearcli == "/opt/bearcli"


def test_bad_poll_falls_back(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('poll_seconds = "soon"\n')
    assert Config.load(path).poll_seconds == 5
    path.write_text("poll_seconds = -3\n")
    assert Config.load(path).poll_seconds == 0


def test_xdg_config_home_is_honoured(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "bjorn" / "config.toml"


def test_editor_resolution_order():
    assert resolve_editor(Config(), {}) == "vim"
    assert resolve_editor(Config(), {"EDITOR": "nano"}) == "nano"
    assert resolve_editor(Config(), {"EDITOR": "nano", "VISUAL": "code -w"}) == "code -w"
    assert resolve_editor(Config(editor="hx"), {"EDITOR": "nano", "VISUAL": "code -w"}) == "hx"
    assert editor_available("python3") and not editor_available("no-such-editor-xyz")
    assert editor_available("python3 -c pass")
