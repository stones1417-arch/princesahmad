__all__ = ["CommunicationService"]


def __getattr__(name):
	if name == "CommunicationService":
		from .communication_service import CommunicationService

		return CommunicationService
	raise AttributeError(name)