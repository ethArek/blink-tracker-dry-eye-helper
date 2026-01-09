import logging
import logging.handlers
import os


def setup_logging(output_dir: str) -> tuple[logging.Logger, logging.Logger, logging.Logger]:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app_logger = logging.getLogger("app")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    blink_handler = logging.handlers.RotatingFileHandler(
        os.path.join(output_dir, "blink_events.log"),
        maxBytes=1_000_000,
        backupCount=3,
    )
    blink_handler.setFormatter(formatter)
    blink_logger = logging.getLogger("blink_events")
    blink_logger.setLevel(logging.INFO)
    blink_logger.addHandler(blink_handler)
    blink_logger.propagate = False

    aggregate_handler = logging.handlers.RotatingFileHandler(
        os.path.join(output_dir, "aggregate_metrics.log"),
        maxBytes=1_000_000,
        backupCount=3,
    )
    aggregate_handler.setFormatter(formatter)
    aggregate_logger = logging.getLogger("aggregate_metrics")
    aggregate_logger.setLevel(logging.INFO)
    aggregate_logger.addHandler(aggregate_handler)
    aggregate_logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    # Ensure there is exactly one console StreamHandler attached to app_logger
    app_logger.handlers = [
        h for h in app_logger.handlers
        if not isinstance(h, logging.StreamHandler)
    ]
    app_logger.addHandler(console_handler)
    return app_logger, blink_logger, aggregate_logger
