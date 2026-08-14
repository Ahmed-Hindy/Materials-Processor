"""Tests for the top-level Materials Processor CLI."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

import materials_processor
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

    exit_code = cli.main(
        [
            "blender",
            "export-usd",
            str(scene),
            "--target",
            "materialx",
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )

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


def test_top_level_cli_maya_export_dispatches(monkeypatch, tmp_path, capsys):
    scene = tmp_path / "scene.ma"
    scene.write_text("// fake maya scene", encoding="utf-8")
    captured = {}

    def fake_export(args):
        captured["args"] = args
        return {
            "scene": args.scene,
            "usd_files": {"openpbr": {"path": "maya_scene_openpbr.usda"}},
        }

    monkeypatch.setattr(cli.maya_cli, "run_export_from_args", fake_export)

    exit_code = cli.main(
        [
            "maya",
            "export-usd",
            str(scene),
            "--target",
            "openpbr",
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    assert captured["args"].maya_command == "export-usd"
    assert captured["args"].target == ["openpbr"]
    assert json.loads(capsys.readouterr().out)["usd_files"]["openpbr"]["path"] == "maya_scene_openpbr.usda"


def test_top_level_cli_maya_inspect_dispatches(monkeypatch, tmp_path, capsys):
    scene = tmp_path / "scene.ma"
    scene.write_text("// fake maya scene", encoding="utf-8")
    captured = {}

    def fake_inspect(args):
        captured["args"] = args
        return {"scene": args.scene, "graph_count": 1}

    monkeypatch.setattr(cli.maya_cli, "run_inspect_from_args", fake_inspect)

    exit_code = cli.main(["maya", "inspect", str(scene), "--missing-textures", "error"])

    assert exit_code == 0
    assert captured["args"].maya_command == "inspect"
    assert captured["args"].missing_textures == "error"
    assert json.loads(capsys.readouterr().out)["graph_count"] == 1


def test_top_level_cli_doctor_reports_runtime_warnings(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_doctor_blender", lambda args: {"dcc": "blender", "status": "missing"})
    monkeypatch.setattr(cli, "_doctor_maya", lambda args: {"dcc": "maya", "status": "found"})
    monkeypatch.setattr(cli, "_doctor_houdini", lambda args: {"dcc": "houdini", "status": "missing"})

    exit_code = cli.main(["doctor"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["package"]["version"] == materials_processor.__version__
    assert payload["runtimes"] == [
        {"dcc": "blender", "status": "missing"},
        {"dcc": "maya", "status": "found"},
        {"dcc": "houdini", "status": "missing"},
    ]


def test_doctor_houdini_validation_keeps_executable_and_hfs_separate(monkeypatch, tmp_path):
    hython = tmp_path / "hython.exe"
    hython.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        cli, "_validate_houdini_runtime", lambda path, timeout: {"version": "21.0.631", "hfs": "C:/HFS"}
    )

    assert cli._doctor_houdini(Namespace(hython=str(hython), validate=True, timeout=3)) == {
        "dcc": "houdini",
        "hfs": "C:/HFS",
        "hython": str(hython.resolve()),
        "status": "valid",
        "version": "21.0.631",
    }


def test_top_level_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])

    assert exc.value.code == 0
    assert f"materials-processor {materials_processor.__version__}" in capsys.readouterr().out


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
    assert "doctor" in help_text
    assert "maya" in help_text
    assert "runtime" in help_text
