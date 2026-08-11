from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderResult:
    status: str
    provider_message_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class BaseCommunicationProvider(ABC):
    @abstractmethod
    def send_sms(self, *, recipient: str, message: str) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def send_whatsapp(self, *, recipient: str, message: str) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def send_email(
        self, *, recipient: str, subject: str, message: str
    ) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def normalize_response(self, response: Any) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, bool]:
        raise NotImplementedError