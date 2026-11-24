"""Errors that are the user's to fix: the command line prints the message alone, with no type name."""


class UserError(ValueError):
    """A problem with what the user asked for (an unknown name, a tool that is not installed, a command
    that fails). The message says what to do about it."""


class MissingTool(UserError, FileNotFoundError):
    """A program the user asked for is not installed."""


class ToolFailed(UserError, RuntimeError):
    """A tool the user asked for ran and failed; the message carries the tool's own error."""
