"""Unit tests for local Houdini executable discovery."""

from __future__ import annotations

from materials_processor.dcc.houdini import runtime


def _disable_ambient_discovery(monkeypatch, tmp_path) -> None:
    """Ensure a test only observes the discovery route it configures."""
    monkeypatch.delenv(runtime.HFS_ENV_VAR, raising=False)
    monkeypatch.delenv(runtime.HYTHON_ENV_VAR, raising=False)
    monkeypatch.delenv(runtime.HUSK_ENV_VAR, raising=False)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: None)
    monkeypatch.setattr(runtime, "DEFAULT_INSTALL_ROOT", tmp_path / "missing_install_root")


def test_resolve_hython_uses_explicit_path(monkeypatch, tmp_path):
    """An explicit Hython path has priority over every discovery route."""
    _disable_ambient_discovery(monkeypatch, tmp_path)
    executable = tmp_path / "hython.exe"
    executable.touch()

    assert runtime.resolve_hython(executable) == executable.resolve()


def test_resolve_hython_uses_environment_override(monkeypatch, tmp_path):
    """The configured Hython executable works without a PATH entry."""
    _disable_ambient_discovery(monkeypatch, tmp_path)
    executable = tmp_path / "configured_hython.exe"
    executable.touch()
    monkeypatch.setenv(runtime.HYTHON_ENV_VAR, str(executable))

    assert runtime.resolve_hython() == executable.resolve()


def test_resolve_husk_uses_active_houdini_install(monkeypatch, tmp_path):
    """Resolves Husk from the active Houdini installation configured by HFS."""
    _disable_ambient_discovery(monkeypatch, tmp_path)
    hfs = tmp_path / "houdini"
    executable = hfs / "bin" / "husk.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setenv(runtime.HFS_ENV_VAR, str(hfs))

    assert runtime.resolve_husk() == executable.resolve()


def test_resolve_hython_prefers_the_newest_supported_install(monkeypatch, tmp_path):
    """Installed Houdini versions are compared numerically, not lexicographically."""
    _disable_ambient_discovery(monkeypatch, tmp_path)
    older = tmp_path / "Houdini 21.0.9" / "bin" / "hython.exe"
    newer = tmp_path / "Houdini 21.0.631" / "bin" / "hython.exe"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.touch()
    newer.touch()
    monkeypatch.setattr(runtime, "DEFAULT_INSTALL_ROOT", tmp_path)

    assert runtime.resolve_hython() == newer.resolve()
