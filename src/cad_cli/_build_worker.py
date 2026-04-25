"""Subprocess worker that loads a model in an arbitrary Python interpreter.

This module is executed by `cad build --python PATH` to keep model evaluation
in an operator-supplied virtual environment while cad-cli's own interpreter
handles I/O and downstream exports. The worker reads its invocation spec from
a JSON file (path supplied as argv[1]), imports the model source, calls the
build callable, and writes the resulting shape to STEP — the artifact format
that crosses the process boundary cleanly.

The worker is intentionally dependency-light: it only imports `build123d`
(which the user's venv must provide) for the STEP export step. cad-cli is
*not* expected to be installed in the user venv; the script is shipped to the
subprocess via `python -c <script>`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

REQUIRED_SHAPE_ATTRS = ("bounding_box", "center", "faces", "solids", "volume")


def main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text())

    model_path = Path(spec["model_path"])
    callable_name = spec["callable_name"]
    step_path = spec["step_path"]
    params = spec["params"]

    module_spec = importlib.util.spec_from_file_location(model_path.stem, model_path)
    if module_spec is None or module_spec.loader is None:
        sys.stderr.write(f"Unable to import model source: {model_path}\n")
        return 2
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    build_callable = getattr(module, callable_name, None)
    if build_callable is None or not callable(build_callable):
        sys.stderr.write(
            f"Model source must expose a callable named '{callable_name}(params, context)'\n"
        )
        return 2

    context = types.SimpleNamespace(
        source_path=spec["source_path"],
        output_dir=spec["output_dir"],
        callable_name=callable_name,
    )
    shape = build_callable(params, context)
    if not all(hasattr(shape, attr) for attr in REQUIRED_SHAPE_ATTRS):
        sys.stderr.write("Model callable did not return a build123d shape/part/compound\n")
        return 5

    try:
        from build123d import export_step
    except ImportError as exc:
        sys.stderr.write(
            "The interpreter passed via --python does not have build123d installed: "
            f"{exc}\n"
        )
        return 3
    export_step(shape, step_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - entered via subprocess
    raise SystemExit(main(sys.argv[1]))
