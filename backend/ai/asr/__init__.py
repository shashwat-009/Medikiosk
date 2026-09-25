"""
MediSetu ASR (Automatic Speech Recognition) module.

Provides provider-independent speech-to-text functionality
for the MediSetu clinical history-taking platform.
"""

from .schemas import ASRResponse
from .base import ASRProvider

__all__ = [
    "ASRResponse",
    "ASRProvider",
]