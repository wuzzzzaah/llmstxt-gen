"""Tiny calculator module used by codexa tests."""

from typing import Final

PI: Final[float] = 3.14159


def add(a: int, b: int = 0) -> int:
    """Return the sum of ``a`` and ``b``."""
    return a + b


async def fetch(url: str) -> str:
    """Pretend to fetch a URL."""
    return url


def _private_helper(x: int) -> int:
    return x * 2


class Calculator:
    """A small stateful calculator."""

    def __init__(self, start: int = 0) -> None:
        self.value = start

    def add(self, n: int) -> int:
        """Add ``n`` to the running value."""
        self.value += n
        return self.value

    @property
    def doubled(self) -> int:
        """Return the value doubled."""
        return self.value * 2

    def _internal(self) -> None:
        pass
