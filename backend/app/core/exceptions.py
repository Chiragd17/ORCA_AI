class OrcaBaseException(Exception):
    """Base exception for all ORCA application errors."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

class ProviderError(OrcaBaseException):
    """Raised when an external data or AI provider fails."""
    pass

class VerificationError(OrcaBaseException):
    """Raised when scientific verification detects a critical anomaly or failure."""
    pass

class AgentExecutionError(OrcaBaseException):
    """Raised when a specialist agent fails during task execution."""
    pass

class ResourceNotFoundError(OrcaBaseException):
    """Raised when a requested resource is not found in storage."""
    pass
