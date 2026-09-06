"""Shared error types for the bridge."""


class BridgeError(Exception):
    """User-facing tool failure. Message is returned to the MCP client as-is."""

    def __init__(self, message: str, *, code: str = "bridge_error"):
        super().__init__(message)
        self.code = code
