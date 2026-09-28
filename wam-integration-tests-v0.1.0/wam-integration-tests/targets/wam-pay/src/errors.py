class ValidationError(ValueError):
    """Invalid input; safe to return to the local client."""


class ConflictError(Exception):
    pass


class NodeUnavailable(Exception):
    """An incomplete or unsafe node snapshot; do not update invoices."""
