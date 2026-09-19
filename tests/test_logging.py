import logging
import tempfile
import unittest
from pathlib import Path

import app.logger_setup as logger_setup


class TestLogging(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_log_dir = logger_setup.LOG_DIR
        self.original_log_file = logger_setup.LOG_FILE
        logger_setup.LOG_DIR = self.temp_dir
        logger_setup.LOG_FILE = self.temp_dir / "vacnet.log"
        self.logger_name = f"vacnet.test.{self._testMethodName}"

    def tearDown(self):
        logger = logging.getLogger(self.logger_name)
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
        logger_setup._CONFIGURED_LOGGERS.discard(self.logger_name)
        logger_setup.LOG_DIR = self.original_log_dir
        logger_setup.LOG_FILE = self.original_log_file

    def test_setup_is_idempotent_and_routes_files(self):
        logger = logger_setup.setup_logger(self.logger_name)
        handler_count = len(logger.handlers)
        same_logger = logger_setup.setup_logger(self.logger_name)

        self.assertIs(logger, same_logger)
        self.assertEqual(len(logger.handlers), handler_count)
        logger.info("routine event")
        logger.error("failed event")

        self.assertIn("routine event", (self.temp_dir / "all.log").read_text(encoding="utf-8"))
        self.assertIn("routine event", (self.temp_dir / "bot.log").read_text(encoding="utf-8"))
        self.assertIn("failed event", (self.temp_dir / "error.log").read_text(encoding="utf-8"))

    def test_read_log_lines_filters_by_level(self):
        logger = logger_setup.setup_logger(self.logger_name)
        logger.info("info event")
        logger.warning("warning event")

        entries = logger_setup.read_log_lines("bot", "WARNING", 20)

        self.assertTrue(any("warning event" in entry for entry in entries))
        self.assertFalse(any("info event" in entry for entry in entries))


if __name__ == "__main__":
    unittest.main()
