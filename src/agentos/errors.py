"""Error types. Each carries the CLI exit code it maps to."""


class AgentOSError(Exception):
    exit_code = 1

    def __init__(self, message: str, exit_code: int | None = None):
        super().__init__(message)
        self.message = message
        if exit_code is not None:
            self.exit_code = exit_code


class UsageError(AgentOSError):
    exit_code = 2


class NotInitialized(AgentOSError):
    exit_code = 2


class PolicyDenied(AgentOSError):
    exit_code = 3

    def __init__(self, message: str, reasons: list[str] | None = None):
        super().__init__(message)
        self.reasons = list(reasons or [])


class NotFound(AgentOSError):
    exit_code = 4


class IntegrityError(AgentOSError):
    exit_code = 5
