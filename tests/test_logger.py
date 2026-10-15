"""Unit tests for EventLogger and CSV logging behavior."""

import csv
import os
import shutil
import tempfile
import unittest
from datetime import datetime

from logger import EventLogger, FIELDS, new_session_id


class TestEventLogger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.temp_dir, "logs", "test_events.csv")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_file_with_header_when_new(self):
        logger = EventLogger(path=self.log_path)
        self.assertTrue(logger.enabled)
        logger.close()

        self.assertTrue(os.path.exists(self.log_path))
        with open(self.log_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header, FIELDS)
            # No data rows yet
            with self.assertRaises(StopIteration):
                next(reader)

    def test_appends_without_overwriting_or_duplicating_header(self):
        # Session 1
        logger1 = EventLogger(path=self.log_path, session_id="session-1")
        logger1.log(1, "color_order", "level_start", 1, 0.0, "", "test detail 1")
        logger1.close()

        # Session 2
        logger2 = EventLogger(path=self.log_path, session_id="session-2")
        logger2.log(2, "grid_path", "grid_move", 1, 1.25, "moved", "dir=up")
        logger2.close()

        # Read back all rows
        with open(self.log_path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        self.assertEqual(len(rows), 3)  # 1 header + 2 data rows
        self.assertEqual(rows[0], FIELDS)
        self.assertEqual(rows[1][1], "session-1")
        self.assertEqual(rows[1][2], "1")
        self.assertEqual(rows[1][3], "color_order")
        self.assertEqual(rows[1][4], "level_start")

        self.assertEqual(rows[2][1], "session-2")
        self.assertEqual(rows[2][2], "2")
        self.assertEqual(rows[2][3], "grid_path")
        self.assertEqual(rows[2][4], "grid_move")

    def test_schema_and_column_count(self):
        logger = EventLogger(path=self.log_path)
        logger.log(0, "", "session_start", None, 0.0, "", "")
        logger.log(1, "color_order", "button_press", 1, 3.456, "correct_step", "selected=blue;expected=blue")
        logger.close()

        with open(self.log_path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        for row in rows:
            self.assertEqual(len(row), len(FIELDS))

    def test_timestamp_is_valid_iso(self):
        logger = EventLogger(path=self.log_path)
        logger.log(1, "color_order", "level_start", 1, 0.0)
        logger.close()

        with open(self.log_path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        ts_str = rows[1][0]
        # Should parse without error
        dt = datetime.fromisoformat(ts_str)
        self.assertIsNotNone(dt)

    def test_new_session_id_format(self):
        sid1 = new_session_id()
        sid2 = new_session_id()
        self.assertNotEqual(sid1, sid2)
        self.assertIn("-", sid1)


if __name__ == "__main__":
    unittest.main()
