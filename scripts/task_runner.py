"""Run GUI-side generators with one background operation at a time.

Generators touch widgets only on the Qt thread; yielded callables touch services
only on the worker. Cancelled results can never resume a stopped generator.
"""
from __future__ import annotations

from functools import wraps
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Qt

from scripts.task_control import ControlInterrupted


def background_action(function):
    @wraps(function)
    def dispatch(self, *args, **kwargs):
        if self.task_runner.busy:
            if function.__name__ not in ("check_game_process", "advance_game_navigation"):
                self.write_log("当前操作仍在处理中，请等待完成或停止任务。")
            return
        if function.__name__ not in ("check_game_process", "advance_game_navigation", "manual_resync", "_resume_navigation"):
            self.game_process_timer.stop()
            self.navigation_timer.stop()
            if function.__name__ != "_resume_interrupted":
                self.workflow.progress.reset()
                self._resume_step = None
        if function.__name__ in ("_run_debug_step", "_run_wegame_post_process", "_dbg_rename_pak", "_run_stage_four"):
            self.workflow.game_navigator.cancel()
        self.task_runner.start(function(self, *args, **kwargs))
    return dispatch


class TaskRunner(QObject):
    progress = Signal(str)
    completed = Signal(object)
    busy_changed = Signal(bool)
    failed = Signal(str)

    def __init__(self, control, parent=None):
        super().__init__(parent)
        self.control = control
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dfAmmo")
        self.generator = None
        self.future = None
        self.closed = False
        self.completed.connect(self._complete, Qt.ConnectionType.QueuedConnection)

    @property
    def busy(self):
        return self.generator is not None or self.future is not None

    def start(self, generator):
        if self.busy or self.closed:
            generator.close()
            return
        self.control.cancelled.clear()
        self.generator = generator
        self.busy_changed.emit(True)
        self._advance()

    def _advance(self, value=None, error=None):
        try:
            operation = self.generator.throw(error) if error else self.generator.send(value)
            self.future = self.executor.submit(self._execute, operation)
            self.future.add_done_callback(self._notify_completed)
        except StopIteration:
            self.generator = None
            self.busy_changed.emit(False)
        except ControlInterrupted:
            self.generator = None
            self.busy_changed.emit(False)
        except Exception as exc:
            self.generator = None
            self.busy_changed.emit(False)
            self.failed.emit(str(exc))

    def _execute(self, operation):
        self.control.check()
        result = operation()
        self.control.check()
        return result

    def _notify_completed(self, future):
        if not self.closed:
            self.completed.emit(future)

    def _complete(self, future):
        if future is not self.future:
            return
        self.future = None
        if self.generator is None:
            self.busy_changed.emit(False)
            return
        try:
            value = future.result()
        except Exception as exc:
            self._advance(error=exc)
        else:
            self._advance(value=value)

    def cancel(self):
        self.control.cancelled.set()
        self.control.paused.clear()
        if self.generator is not None:
            self.generator.close()
            self.generator = None
        self.control.paused.clear()
        if self.future is None:
            self.busy_changed.emit(False)

    def shutdown(self):
        self.cancel()
        self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
