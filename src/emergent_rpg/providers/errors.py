from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for external narrative-provider failures."""


class ProviderConfigurationError(ProviderError):
    """Raised when provider configuration is missing or invalid."""


class ProviderRequestError(ProviderError):
    """Raised when a provider request cannot be completed."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an unusable response."""
