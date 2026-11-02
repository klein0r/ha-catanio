"""Exceptions raised by the CatanIO client."""


class CatanIOError(Exception):
    """Base class for all CatanIO errors."""


class CatanIOConnectionError(CatanIOError):
    """The device could not be reached or did not answer in time."""


class CatanIOResponseError(CatanIOError):
    """The device answered a request with a CoAP error code."""

    def __init__(self, path: str, code: str) -> None:
        """Initialize the error."""
        super().__init__(f"Request to /{path} failed with {code}")
        self.path = path
        self.code = code


class CatanIOProtocolError(CatanIOError):
    """The device answered with a payload that could not be interpreted."""
