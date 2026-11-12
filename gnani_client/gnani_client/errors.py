"""Errors from a live Gnani call. Mock mode does not raise these."""


class GnaniError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body
