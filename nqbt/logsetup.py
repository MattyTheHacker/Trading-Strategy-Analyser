"""Console logging for the CLI and the scripts in ``tools/``.

Results go to stdout so they can be piped or redirected; errors go to stderr. Only entry
points call :func:`configure`; a library module that reports progress (``sweep``) just
logs, and stays silent until something configures a handler.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO


def _below_warning(record: logging.LogRecord) -> bool:
    return record.levelno < logging.WARNING


def configure(*names: str, level: int = logging.INFO) -> None:
    """Route the ``nqbt`` package and ``names`` to stdout, and errors to stderr.

    Pass ``__name__``: a module run as a script logs to ``__main__``, not to its import path.
    Calling this again replaces the handlers rather than doubling them.
    """
    out: logging.StreamHandler[TextIO] = logging.StreamHandler(sys.stdout)
    out.addFilter(_below_warning)
    out.setFormatter(logging.Formatter("%(message)s"))

    err: logging.StreamHandler[TextIO] = logging.StreamHandler(sys.stderr)
    err.setLevel(logging.WARNING)
    err.setFormatter(logging.Formatter("error: %(message)s"))

    logging.basicConfig(level=logging.WARNING, handlers=[out, err], force=True)
    for name in ("nqbt", *names):
        logging.getLogger(name).setLevel(level)
