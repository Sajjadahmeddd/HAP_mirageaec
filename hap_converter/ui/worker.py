"""QThread wrapper around engine.pipeline.convert.

The pipeline runs entirely on this thread; progress callbacks are forwarded
as Qt signals so the main window never freezes. cancel() flips a flag that
the engine polls per page via its cancel_cb hook.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from hap_converter.engine import pipeline
from hap_converter.engine.config import Config


class ConvertWorker(QThread):
    progress = Signal(int, int, str)   # done, total, message
    finished_result = Signal(object)   # pipeline.Result

    def __init__(self, pdf_path: str, output_dir: str, config: Config, parent=None):
        super().__init__(parent)
        self._pdf_path = pdf_path
        self._output_dir = output_dir
        self._config = config
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            result = pipeline.convert(
                self._pdf_path,
                self._output_dir,
                self._config,
                progress_cb=lambda done, total, msg: self.progress.emit(done, total, msg),
                cancel_cb=lambda: self._cancelled,
            )
        except Exception as exc:  # last-resort guard: the UI must always get a reason
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
