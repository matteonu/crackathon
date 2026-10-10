"""The one error type the HTTP layer turns into a response.

Raise it anywhere under /api with a status and a message that is safe to show the user;
app.py has the handler. Anything else becomes a 500 with no detail.
"""


class RequestError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)
