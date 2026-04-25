"""Shared CLI error types and exit code mapping."""

from __future__ import annotations


class CadCliError(Exception):
    """Base error with a stable exit code.

    Errors raised at internal boundaries (model import, callable invocation,
    artifact export) carry the originating traceback and exception identity
    so the CLI can surface them in --format json output without callers
    string-scraping the message.
    """

    exit_code = 1

    def __init__(
        self,
        message: str,
        *,
        traceback_str: str | None = None,
        cause_type: str | None = None,
        cause_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.traceback_str = traceback_str
        self.cause_type = cause_type
        self.cause_message = cause_message


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
