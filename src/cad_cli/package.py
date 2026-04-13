"""Package command implementation."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .artifacts import ensure_directory, iter_files, sha256_file, write_json
from .errors import InputError
from .schemas import PackageEntry, PackageResult


def _collect_entries(role: str, root: Path) -> list[PackageEntry]:
    if not root.exists():
        raise InputError(f"Package input does not exist: {root}")
    entries: list[PackageEntry] = []
    base = root if root.is_dir() else root.parent
    for file_path in iter_files(root):
        relative = file_path.relative_to(base)
        entries.append(
            PackageEntry(
                role=role,
                source_path=str(file_path.resolve()),
                archive_path=str(Path(role) / relative),
                sha256=sha256_file(file_path),
                size_bytes=file_path.stat().st_size,
            )
        )
    return entries


def run_package(
    *,
    output_path: Path,
    build_dir: Path | None,
    render_dir: Path | None,
    compare_dir: Path | None,
    includes: list[Path],
) -> PackageResult:
    # CAD-F-014 / CAD-F-017:
    # package authoritative and presentation artifacts with traceable manifests.
    ensure_directory(output_path.parent)
    manifest_path = output_path.parent / "package-manifest.json"
    entries: list[PackageEntry] = []
    if build_dir is not None:
        entries.extend(_collect_entries("build", build_dir))
    if render_dir is not None:
        entries.extend(_collect_entries("render", render_dir))
    if compare_dir is not None:
        entries.extend(_collect_entries("compare", compare_dir))
    for include in includes:
        entries.extend(_collect_entries("extra", include))
    if not entries:
        raise InputError(
            "Package command needs at least one input via --build-dir, --render-dir, "
            "--compare-dir, or --include"
        )

    result = PackageResult(
        command="package",
        summary=f"Packaged {len(entries)} files into {output_path.name}",
        bundle_path=str(output_path.resolve()),
        manifest_path=str(manifest_path.resolve()),
        inputs={
            "build_dir": str(build_dir.resolve()) if build_dir is not None else None,
            "render_dir": str(render_dir.resolve()) if render_dir is not None else None,
            "compare_dir": str(compare_dir.resolve()) if compare_dir is not None else None,
            "includes": [str(path.resolve()) for path in includes],
        },
        entries=entries,
    )
    write_json(manifest_path, result)
    with ZipFile(output_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.write(manifest_path, arcname="package-manifest.json")
        for entry in entries:
            archive.write(entry.source_path, arcname=entry.archive_path)
    return result
