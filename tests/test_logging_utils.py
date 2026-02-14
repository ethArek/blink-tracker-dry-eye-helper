import logging
import os
import tempfile
import unittest

from blink_app.services.logging_utils import setup_logging


class LoggingSetupTest(unittest.TestCase):
    def tearDown(self) -> None:
        self._reset_logger("app")
        self._reset_logger("blink_events")
        self._reset_logger("aggregate_metrics")

    def test_setup_logging_is_idempotent_for_named_loggers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app_logger, blink_logger, aggregate_logger = setup_logging(tmp_dir)
            app_logger.info("app event")
            blink_logger.info("blink event")
            aggregate_logger.info("aggregate event")

            app_logger, blink_logger, aggregate_logger = setup_logging(tmp_dir)
            app_logger.info("app event after reset")
            blink_logger.info("blink event after reset")
            aggregate_logger.info("aggregate event after reset")

            self._assert_logger_has_expected_handlers(app_logger)
            self._assert_logger_has_expected_handlers(blink_logger)
            self._assert_logger_has_expected_handlers(aggregate_logger)

            app_log_path = os.path.join(tmp_dir, "app.log")
            blink_log_path = os.path.join(tmp_dir, "blink_events.log")
            aggregate_log_path = os.path.join(tmp_dir, "aggregate_metrics.log")
            self.assertTrue(os.path.exists(app_log_path))
            self.assertTrue(os.path.exists(blink_log_path))
            self.assertTrue(os.path.exists(aggregate_log_path))

            self._reset_logger("app")
            self._reset_logger("blink_events")
            self._reset_logger("aggregate_metrics")

    def _assert_logger_has_expected_handlers(self, logger: logging.Logger) -> None:
        self.assertEqual(len(logger.handlers), 2)
        console_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
        ]
        file_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.FileHandler)
        ]
        self.assertEqual(len(console_handlers), 1)
        self.assertEqual(len(file_handlers), 1)

    def _reset_logger(self, name: str) -> None:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    unittest.main()
