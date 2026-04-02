"""Project-specific exception hierarchy."""

class McpMacError(Exception):
    """Base error for macOS integration failures."""


class AutomationPermissionError(McpMacError):
    """Raised when macOS automation permissions are missing."""


class NotFoundError(McpMacError):
    """Raised when a requested resource cannot be found."""


class ValidationError(McpMacError):
    """Raised when tool inputs are invalid."""


class ConflictError(McpMacError):
    """Raised when a request is logically inconsistent."""
