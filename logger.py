"""Timestamped CSV event logging. Appends to one file; never overwrites."""

import csv
import os
import uuid
from datetime import datetime, timezone

FIELDS = ["timestamp", "session_id", "level", "puzzle_type", "action",
          "attempt", "elapsed_s", "outcome", "detail"]

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG_PATH = os.path.join(HERE, "logs", "events.csv")


def new_session_id():
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


class EventLogger:
    def __init__(self, path=DEFAULT_LOG_PATH, session_id=None):
        self.path = path
        self.session_id = session_id or new_session_id()
        self.enabled = False
        self._file = None
        self._writer = None
        self._open()

    def _open(self):
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            needs_header = (not os.path.exists(self.path)
                            or os.path.getsize(self.path) == 0)
            self._file = open(self.path, "a", newline="", encoding="utf-8")
            self._writer = csv.writer(self._file)
            if needs_header:
                self._writer.writerow(FIELDS)
                self._file.flush()
            self.enabled = True
        except OSError as err:
            print(f"Warning: cannot open log file ({err}). Logging is off.")

    def log(self, level, puzzle_type, action, attempt, elapsed_s,
            outcome="", detail=""):
        if not self.enabled:
            return
        row = [
            datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            self.session_id, level, puzzle_type, action,
            "" if attempt is None else attempt,
            f"{elapsed_s:.3f}", outcome, detail,
        ]
        try:
            self._writer.writerow(row)
            self._file.flush()      # keep data safe if the game crashes
        except (OSError, ValueError) as err:
            print(f"Warning: logging failed ({err}). Logging is off.")
            self.enabled = False

    def close(self):
        if self._file:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
        self.enabled = False
