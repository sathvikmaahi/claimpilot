import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """
    Input: level (str) — logging level string e.g. "INFO", "DEBUG".
    Description: Configures root logger to write structured log lines to stdout.
    Output: None — configures logging as a side effect.
    """
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


logger = logging.getLogger("clerk_assistance_pipeline")
