"""Small wheel-safe error contract shared by Fairlight result projectors."""


class FairlightDescriptorError(ValueError):
    """A Fairlight result or verification record failed closed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
