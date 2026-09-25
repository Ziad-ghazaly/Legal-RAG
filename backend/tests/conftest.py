"""Shared pytest fixtures. Grows in later tasks."""

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
