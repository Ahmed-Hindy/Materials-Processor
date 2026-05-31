"""Tests for the top-level Materials Processor CLI."""

from __future__ import annotations

import json
from pathlib import Path

from materials_processor import cli


def test_top_level_cli_blender_export_dispatches(monkeypatch, tmp_path, capsys):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    captured = {}

    def fake_export(args):
        captured["args"] = args
        return {
            "scene": args.scene,
            "usd_files": {"mtlx": {"path": "out.usda"}},
        }

    monkeypatch.setattr(cli.blender_cli, "run_export_from_args", fake_export)

    exit_code = cli.main([
        "blender",
        "export-usd",
        str(scene),
        "--target",
        "materialx",
        "--out-dir",
        str(tmp_path / "out"),
    ])

    assert exit_code == 0
    assert captured["args"].blender_command == "export-usd"
    assert captured["args"].target == ["materialx"]
    assert json.loads(capsys.readouterr().out)["usd_files"]["mtlx"]["path"] == "out.usda"


def test_top_level_cli_blender_inspect_dispatches(monkeypatch, tmp_path, capsys):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    captured = {}

    def fake_inspect(args):
        captured["args"] = args
        return {"scene": args.scene, "graph_count": 1}

    monkeypatch.setattr(cli.blender_cli, "run_inspect_from_args", fake_inspect)

    exit_code = cli.main(["blender", "inspect", str(scene), "--missing-textures", "error"])

    assert exit_code == 0
    assert captured["args"].blender_command == "inspect"
    assert captured["args"].missing_textures == "error"
    assert json.loads(capsys.readouterr().out)["graph_count"] == 1


def test_top_level_cli_runtime_validate_blender_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "_validate_blender_runtime",
        lambda args: {"dcc": "blender", "version": "4.5.0", "material_smoke": args.material_smoke},
    )

    exit_code = cli.main(["runtime", "validate", "--dcc", "blender", "--material-smoke"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "dcc": "blender",
        "material_smoke": True,
        "version": "4.5.0",
    }


def test_top_level_cli_runtime_validate_maya_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_validate_maya_runtime", lambda args: {"dcc": "maya", "version": args.maya_version})

    exit_code = cli.main(["runtime", "validate", "--dcc", "maya", "--maya-version", "2024"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"dcc": "maya", "version": "2024"}


def test_top_level_cli_reports_runtime_errors_without_traceback(monkeypatch, tmp_path, capsys):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")

    def fail(args):
        raise RuntimeError("missing textures")

    monkeypatch.setattr(cli.blender_cli, "run_inspect_from_args", fail)

    exit_code = cli.main(["blender", "inspect", str(scene)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err == "error: missing textures\n"
    assert "Traceback" not in captured.err


def test_top_level_parser_exposes_expected_commands():
    help_text = cli.build_parser().format_help()

    assert "blender" in help_text
    assert "runtime" in help_text
