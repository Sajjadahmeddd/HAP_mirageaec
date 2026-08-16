"""QThread wrappers around the engine's public entry points.

The pipeline runs entirely on the worker thread; progress callbacks are
forwarded as Qt signals so the window never freezes. cancel() flips a flag
that the engine polls per page via its cancel_cb hook.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from hap_converter.engine import pipeline
from hap_converter.engine.config import Config


class ConvertWorker(QThread):
    """New Project: PDF -> schedule."""

    progress = Signal(int, int, str)   # done, total, message
    finished_result = Signal(object)   # pipeline.Result / ChangeResult

    def __init__(self, pdf_path: str, output_dir: str, config: Config, parent=None):
        super().__init__(parent)
        self._pdf_path = pdf_path
        self._output_dir = output_dir
        self._config = config
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _emit_progress(self, done: int, total: int, message: str) -> None:
        self.progress.emit(done, total, message)

    def _work(self):
        return pipeline.convert(
            self._pdf_path,
            self._output_dir,
            self._config,
            progress_cb=self._emit_progress,
            cancel_cb=lambda: self._cancelled,
        )

    def run(self) -> None:
        try:
            result = self._work()
        except Exception as exc:  # last-resort guard: the UI must get a reason
            result = pipeline.Result(
                ok=False,
                output_path=None,
                issues=[
                    pipeline.Issue(
                        page=0,
                        field="error",
                        description=f"Unexpected error during conversion: {exc}",
                    )
                ],
                stats={},
            )
        self.finished_result.emit(result)


class ChangeRequestWorker(ConvertWorker):
    """Change Request: append a revised PDF to an existing schedule."""

    def __init__(
        self, xlsx_path: str, pdf_path: str, output_dir: str, config: Config, parent=None
    ):
        super().__init__(pdf_path, output_dir, config, parent)
        self._xlsx_path = xlsx_path

    def _work(self):
        return pipeline.convert_change_request(
            self._xlsx_path,
            self._pdf_path,
            self._output_dir,
            self._config,
            progress_cb=self._emit_progress,
            cancel_cb=lambda: self._cancelled,
        )
