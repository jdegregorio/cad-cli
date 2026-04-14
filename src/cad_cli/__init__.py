"""cad-cli package."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    # Read version from the installed package metadata so pyproject.toml is
    # the single source of truth (release-please bumps it during a release).
    __version__ = _pkg_version("cad-cli")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0+unknown"

__all__ = ["__version__"]
