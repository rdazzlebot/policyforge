"""Whether a cited passage actually supports the claim made from it."""

from .base import (
    CONTRADICTED,
    ENTAILED,
    NEUTRAL,
    Entailer,
    Unsupported,
    Verdict,
    get_entailer,
    unsupported_claims,
)

__all__ = [
    "CONTRADICTED",
    "ENTAILED",
    "NEUTRAL",
    "Entailer",
    "Unsupported",
    "Verdict",
    "get_entailer",
    "unsupported_claims",
]
