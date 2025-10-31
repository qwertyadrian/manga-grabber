class GrabberException(Exception):
    """Base exception for the manga grabber library"""

    pass


class TitleNotFoundError(GrabberException):
    """Exception raised when a title is not found"""

    pass


class ChapterInfoError(GrabberException):
    """Exception raised when there is an error retrieving chapter information"""

    pass
