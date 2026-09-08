"""Private descriptor validation errors, kept outside the public inventory package."""


class FusionDescriptorValidationError(ValueError):
    """A signed Fusion descriptor or its private runtime binding is invalid."""
