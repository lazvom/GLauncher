"""
Lightweight concurrent task manager.

Every install/download runs in its own daemon thread the moment it's started, so
several can be in flight at once (e.g. installing one instance while downloading a
mod into another and installing a modpack into a third). Nothing here ever grabs
the UI - progress is reported through a thread-safe queue that the UI drains from
its own main-thread loop (never touching widgets from a background thread, which
Tkinter doesn't support safely), so it can render everything inline instead of a
blocking pop-up.
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Task:
    id: str
    title: str
    kind: str = "generic"          # "install_instance" | "install_content" | "install_modpack" | "launch" | ...
    ref_id: Optional[str] = None   # e.g. instance id, so the UI can find "my" task
    status: str = "running"        # running | done | error
    progress: Optional[float] = None  # 0..1, or None for indeterminate
    detail: str = ""
    error: Optional[str] = None
    result: Any = None             # whatever work_fn returns, once done
    created_at: float = field(default_factory=time.time)


class TaskManager:
    def __init__(self):
        self.tasks: "dict[str, Task]" = {}
        self._queue: "queue.Queue[Task]" = queue.Queue()
        self._lock = threading.Lock()

    def active_count(self) -> int:
        return sum(1 for t in self.tasks.values() if t.status == "running")

    def start(self, title: str, work_fn: Callable[[Callable], Any], kind: str = "generic",
              ref_id: Optional[str] = None) -> str:
        """Runs work_fn(update) in a new background thread immediately and returns a task id.
        work_fn should call update(progress, detail) as it makes progress (0..1 float, or
        None for "working, no percentage available"), and may return a value that ends up
        as task.result. work_fn must NOT touch any UI widgets directly - only call update()."""
        task_id = str(uuid.uuid4())
        task = Task(id=task_id, title=title, kind=kind, ref_id=ref_id)
        with self._lock:
            self.tasks[task_id] = task
        self._queue.put(task)

        def update(progress: Optional[float] = None, detail: str = ""):
            task.progress = progress
            task.detail = detail
            self._queue.put(task)

        def runner():
            try:
                result = work_fn(update)
                task.result = result
                task.status = "done"
                task.progress = 1.0
            except Exception as e:
                task.status = "error"
                task.error = str(e)
                task.detail = str(e)
            self._queue.put(task)

        threading.Thread(target=runner, daemon=True).start()
        return task_id

    def drain(self) -> list:
        """Call ONLY from the UI's main thread (e.g. on a periodic self.after loop).
        Returns every task update queued since the last call."""
        items = []
        try:
            while True:
                items.append(self._queue.get_nowait())
        except queue.Empty:
            pass
        return items

    def get_for_ref(self, ref_id: str) -> Optional[Task]:
        """Latest still-running (or most recent) task tied to a given ref_id (e.g. instance id)."""
        candidates = [t for t in self.tasks.values() if t.ref_id == ref_id]
        if not candidates:
            return None
        running = [t for t in candidates if t.status == "running"]
        if running:
            return max(running, key=lambda t: t.created_at)
        return max(candidates, key=lambda t: t.created_at)
