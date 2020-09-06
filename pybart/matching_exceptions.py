class Mismatch(Exception):
    """Base class for other mismatch exceptions"""
    pass


class LabelMismatch(Mismatch):
    """Raised when the Label constraint is mismatched"""
    pass


class RequiredTokenMismatch(Mismatch):
    """Raised when there was no match for a required token"""
    pass
