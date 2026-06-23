class ServiceEventNotFoundError(Exception):
    """Raised when a service_event_id has no matching row in progress_notes or service_metadata."""


class AuthAPIUnavailableError(Exception):
    """Raised when the mock Medicaid authorization API cannot be reached or times out."""


class ValidationFailure:
    """A single validation check failure — check number and reason for clerk display."""

    def __init__(self, check: int, reason: str) -> None:
        self.check = check
        self.reason = reason

    def __repr__(self) -> str:
        return f"ValidationFailure(check={self.check}, reason={self.reason!r})"


class ValidationFailedError(Exception):
    """Raised when a service event fails one or more Pipeline B validation checks.
    Always carries the full list of failures so the clerk sees all issues at once.
    """

    def __init__(self, failures: list["ValidationFailure"]) -> None:
        if not failures:
            raise ValueError("ValidationFailedError requires at least one failure")
        self.failures = failures
        super().__init__(repr(failures))


class ClaimBuildError(Exception):
    """Raised when the Claim Builder agent cannot produce a valid 837P EDI file."""
