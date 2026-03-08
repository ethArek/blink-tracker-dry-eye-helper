import logging
import os
import unittest
from unittest.mock import patch

from blink_app.services.logging_utils import setup_logging


class DummyFileHandler(logging.Handler):
    def __init__(self, filename: str, *args, **kwargs) -> None:
        super().__init__()
        self.baseFilename = os.path.abspath(filename)
        self.was_closed = False

    def emit(self, record: logging.LogRecord) -> None:
        return

    def close(self) -> None:
        self.was_closed = True
        super().close()


class LoggingSetupTest(unittest.TestCase):
    def tearDown(self) -> None:
        self._reset_logger("app")
        self._reset_logger("blink_events")
        self._reset_logger("aggregate_metrics")

    def test_setup_logging_is_idempotent_for_named_loggers(self) -> None:
        created_file_handlers: list[DummyFileHandler] = []

        def build_file_handler(filename: str, *args, **kwargs) -> DummyFileHandler:
            handler = DummyFileHandler(filename, *args, **kwargs)
            created_file_handlers.append(handler)
            return handler

        output_dir = os.path.join("C:\\", "virtual-output")
        with patch(
            "blink_app.services.logging_utils.logging.handlers.RotatingFileHandler",
            side_effect=build_file_handler,
        ):
            app_logger, blink_logger, aggregate_logger = setup_logging(output_dir)
            first_app_handler = self._file_handler_for(app_logger)
            first_blink_handler = self._file_handler_for(blink_logger)
            first_aggregate_handler = self._file_handler_for(aggregate_logger)

            app_logger.info("app event")
            blink_logger.info("blink event")
            aggregate_logger.info("aggregate event")

            app_logger, blink_logger, aggregate_logger = setup_logging(output_dir)
            app_logger.info("app event after reset")
            blink_logger.info("blink event after reset")
            aggregate_logger.info("aggregate event after reset")

        self._assert_logger_has_expected_handlers(app_logger)
        self._assert_logger_has_expected_handlers(blink_logger)
        self._assert_logger_has_expected_handlers(aggregate_logger)

        self.assertEqual(first_app_handler.baseFilename, os.path.abspath(os.path.join(output_dir, "app.log")))
        self.assertEqual(first_blink_handler.baseFilename, os.path.abspath(os.path.join(output_dir, "blink_events.log")))
        self.assertEqual(
            first_aggregate_handler.baseFilename,
            os.path.abspath(os.path.join(output_dir, "aggregate_metrics.log")),
        )
        self.assertTrue(first_app_handler.was_closed)
        self.assertTrue(first_blink_handler.was_closed)
        self.assertTrue(first_aggregate_handler.was_closed)
        self.assertEqual(len(created_file_handlers), 6)

    def _assert_logger_has_expected_handlers(self, logger: logging.Logger) -> None:
        self.assertEqual(len(logger.handlers), 2)
        console_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, DummyFileHandler)
        ]
        file_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler, DummyFileHandler)
        ]
        self.assertEqual(len(console_handlers), 1)
        self.assertEqual(len(file_handlers), 1)

    @staticmethod
    def _file_handler_for(logger: logging.Logger) -> DummyFileHandler:
        for handler in logger.handlers:
            if isinstance(handler, DummyFileHandler):
                return handler

        raise AssertionError("Expected a dummy file handler.")

    @staticmethod
    def _reset_logger(name: str) -> None:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    unittest.main()
