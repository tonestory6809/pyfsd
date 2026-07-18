"""Client session."""

from typing import TYPE_CHECKING, Protocol

from pyfsd.define.protocol.packet import ClientBoundPacket

if TYPE_CHECKING:
    from pyfsd.client.object import Client

__all__ = ["ClientSession"]


class ClientSession(Protocol):
    """Session of a client, which accepts requests (incoming packets, kill request, etc)."""

    def send_packets(self, *packets: ClientBoundPacket) -> None:
        """Handle incoming packets."""
        raise NotImplementedError

    def kill(self) -> None:
        """Kill the client, in a peaceful way."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the connection of the client immediately."""
        raise NotImplementedError

    def get_description(self) -> str:
        """Get text representation of the client."""
        raise NotImplementedError

    def get_client(self) -> "Client | None":
        """Get the client behind the session."""
        raise NotImplementedError
