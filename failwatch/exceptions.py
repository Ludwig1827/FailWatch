from typing import Dict, Optional


class FailWatchError(Exception):
    def __init__(
        self,
        message: str,
        analysis: Optional[Dict] = None,
        context: Optional[Dict] = None,
    ):
        super().__init__(message)
        self.analysis = analysis or {}
        self.context = context or {}


class FailWatchBlocked(FailWatchError):
    pass


class FailWatchRejected(FailWatchError):
    pass


class FailWatchReviewPending(FailWatchError):
    pass


class FailWatchConnectionError(FailWatchError):
    pass
