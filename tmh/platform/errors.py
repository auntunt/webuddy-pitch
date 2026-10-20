"""The one error every layer may raise toward the HTTP API: a status code and a message for people."""


class ApiError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
