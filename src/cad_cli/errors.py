"""Shared CLI error types and exit code mapping."""

from __future__ import annotations


class CadCliError(Exception):
    """Base error with a stable exit code."""

    exit_code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InputError(CadCliError):
    """Invalid user input or unsupported CLI contract."""

    exit_code = 2


class MissingDependencyError(CadCliError):
    """A required binary or library is unavailable."""

    exit_code = 3


class UnsupportedOperationError(CadCliError):
    """The input type is supported by the CLI but not for the requested operation."""

    exit_code = 4


class GeometryError(CadCliError):
    """Geometry build, load, export, or inspection failure."""

    exit_code = 5


class RenderError(CadCliError):
    """Render pipeline failure."""

    exit_code = 6


class CompareError(CadCliError):
    """Comparison pipeline failure."""

    exit_code = 7
