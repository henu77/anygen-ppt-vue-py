class ApiError(Exception):
    def __init__(self, message: str, code: int = 400):
        self.code = code
        self.message = message
        super().__init__(message)
