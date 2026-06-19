class ServiceEventNotFoundError(Exception):
    """Raised when a service_event_id has no matching row in progress_notes or service_metadata."""


class AuthAPIUnavailableError(Exception):
    """Raised when the mock Medicaid authorization API cannot be reached or times out."""


class ValidationFailedError(Exception):
    """Raised when a service event fails one or more of the 5 Pipeline B validation checks."""


class ClaimBuildError(Exception):
    """Raised when the Claim Builder agent cannot produce a valid 837P EDI file."""
