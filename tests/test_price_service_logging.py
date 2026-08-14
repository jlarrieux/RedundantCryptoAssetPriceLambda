import logging

import pytest

from price_service import PriceService


@pytest.fixture
def logger():
    """Provide an isolated PriceService logger without leaking global state."""
    logger = logging.getLogger("PriceService")
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    logger.handlers.clear()
    try:
        yield logger
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)
        logger.propagate = original_propagate


def test_price_service_logger_handler_count_is_stable(logger):
    PriceService()
    PriceService()

    assert len(logger.handlers) == 1
    assert logger.propagate is False
