from __future__ import annotations

import json

from cad_cli.cli import build_parser, main


def test_parser_requires_subcommand() -> None:
    parser = build_parser()
    try:
        parser.parse_args([])
    except Exception as exc:  # noqa: BLE001
        assert "required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected parser failure without a subcommand")


def test_main_returns_input_error_for_missing_model() -> None:
    exit_code = main(["build", "missing.py", "--output-dir", "out"])
    assert exit_code == 2


def test_main_json_output_for_helpful_command(tmp_path, capsys, examples_dir) -> None:
    output_dir = tmp_path / "build"
    exit_code = main(
        [
            "build",
            str(examples_dir / "box.py"),
            "--output-dir",
            str(output_dir),
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["command"] == "build"
    assert payload["schema_version"] == 1
