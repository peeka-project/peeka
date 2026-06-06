"""Attach progress event helpers."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

def _attach_module():
    from peeka.core import attach as attach_module

    return attach_module


class AttachProgressMixin:

    def _emit_progress(
        self,
        phase: str,
        status: str,
        message: str,
        *,
        level: str = "info",
        elapsed_ms: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Any:
        event = _attach_module().AttachProgressEvent(
            phase=phase,
            status=status,
            message=message,
            level=level,
            elapsed_ms=elapsed_ms,
            details=details or {},
        )
        self.progress_events.append(event)
        if len(self.progress_events) > _attach_module()._MAX_PROGRESS_EVENTS:
            del self.progress_events[: len(self.progress_events) - _attach_module()._MAX_PROGRESS_EVENTS]
        if self.progress_callback:
            try:
                self.progress_callback(event)
            except Exception:
                if not self._progress_callback_error_active:
                    self._progress_callback_error_active = True
                    try:
                        _attach_module().logger.debug("Attach progress callback failed", exc_info=True)
                    finally:
                        self._progress_callback_error_active = False
        return event

    @contextmanager
    def _progress_phase(
        self,
        phase: str,
        start_message: str,
        done_message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> Iterator[None]:
        start = time.monotonic()
        self._emit_progress(phase, "running", start_message, details=details)
        try:
            yield
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            self._emit_progress(
                phase,
                "failed",
                f"{start_message} failed: {exc}",
                level="error",
                elapsed_ms=elapsed_ms,
                details=details,
            )
            raise
        else:
            elapsed_ms = (time.monotonic() - start) * 1000
            self._emit_progress(
                phase,
                "done",
                done_message,
                elapsed_ms=elapsed_ms,
                details=details,
            )

    @contextmanager
    def _capture_attach_diagnostics(self) -> Iterator[None]:
        """Mirror attach logs and warnings into progress events when requested."""
        if not self.progress_callback:
            yield
            return

        handler = _attach_module()._AttachProgressLogHandler(self)
        old_level = _attach_module().logger.level
        old_showwarning = _attach_module().warnings.showwarning
        old_propagate = _attach_module().logger.propagate

        def showwarning(
            message: Any,
            category: Any,
            filename: str,
            lineno: int,
            file: Any = None,
            line: Optional[str] = None,
        ) -> None:
            self._emit_progress(
                "attach_log",
                "logged",
                str(message),
                level="warning",
                details={
                    "warning": category.__name__,
                    "filename": filename,
                    "lineno": lineno,
                },
            )

        _attach_module().logger.addHandler(handler)
        _attach_module().logger.setLevel(logging.DEBUG)
        _attach_module().logger.propagate = False
        _attach_module().warnings.showwarning = showwarning
        try:
            yield
        finally:
            _attach_module().warnings.showwarning = old_showwarning
            _attach_module().logger.setLevel(old_level)
            _attach_module().logger.propagate = old_propagate
            _attach_module().logger.removeHandler(handler)
