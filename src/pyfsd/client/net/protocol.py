"""PyFSD client protocol."""

import asyncio
import dataclasses
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import (
    TYPE_CHECKING,
    TypeVar,
    cast,
)

from structlog import get_logger
from typing_extensions import assert_never

from pyfsd._version import version as pyfsd_version
from pyfsd.client.object import Client
from pyfsd.define.broadcast import (
    BroadcastChecker,
    all_ATC_checker,
    all_pilot_checker,
    at_checker,
    broadcast_checkers,
    broadcast_message_checker,
    broadcast_position_checker,
    create_broadcast_range_checker,
)
from pyfsd.define.protocol import FSDClientCommand
from pyfsd.define.protocol.errors import FSDClientError
from pyfsd.define.protocol.packet import (
    AddATCPacket,
    AddPilotPacket,
    ATCPositionPacket,
    ClientBoundPacket,
    CloudPacket,
    ErrorPacket,
    FlightPlanPacket,
    KillPacket,
    MulticastPacket,
    PilotPositionPacket,
    RemoveClientPacket,
    ReplyAcarsPacket,
    RequestAcarsPacket,
    ServerBoundPacket,
    ServerClientQueryPacket,
    ServerPingPacket,
    TempPacket,
    WeatherQueryPacket,
    WindPacket,
    try_parse,
)
from pyfsd.define.utils import (
    is_callsign_valid,
    logged_task,
    mustdone_task_keeper,
)
from pyfsd.protocol import LineProtocol

if TYPE_CHECKING:
    from pyfsd.plugin import PluginHandledEventResult, PyFSDHandledEventResult

    from .factory import ClientFactory

TIMEOUT = 500
version_bytes = ("PyFSD " + pyfsd_version).encode("ascii")
logger = get_logger(__name__)

__all__ = ["TIMEOUT", "ClientProtocol", "check_packet"]

HandleResult = tuple[bool, bool]  # (packet_ok, has_result)
_T_ClientProtocol = TypeVar("_T_ClientProtocol", bound="ClientProtocol")
_T_ServerBoundPacket = TypeVar("_T_ServerBoundPacket", bound=ServerBoundPacket)
_PacketHandler = Callable[
    [_T_ClientProtocol, _T_ServerBoundPacket], Awaitable[HandleResult]
]


def check_packet(
    check_callsign: bool = True,
    need_login: bool = True,
) -> Callable[
    [_PacketHandler[_T_ClientProtocol, _T_ServerBoundPacket]],
    _PacketHandler[_T_ClientProtocol, _T_ServerBoundPacket],
]:
    """Create a decorator to perform misc checks.

    Args:
        need_login: Checks if self.client is not None (logined).
        check_callsign: Checks if packet.source == self.client.callsign
    """

    def decorator(func: _PacketHandler) -> _PacketHandler:
        @wraps(func)
        async def realfunc(
            self: "ClientProtocol",
            packet: ServerBoundPacket,
        ) -> HandleResult:
            if need_login:
                if self.client is None:
                    return (False, False)
                if check_callsign and self.client.callsign != packet.source:
                    self.send_error(FSDClientError.SRCINVALID, env=packet.source)
                    return (False, False)
            return await func(self, packet)

        return realfunc

    return decorator


class ClientProtocol(LineProtocol):
    """PyFSD client protocol.

    Attributes:
        factory: The client protocol factory.
        transport: Asyncio transport.
        client: The client info. None before `#AA` or `#AP` to create new client.
        tasks: Processing handle_line tasks.
    """

    factory: "ClientFactory"
    worker_task: asyncio.Task[None] | None
    # TODO: migrate to Queue.shutdown
    worker_queue: asyncio.Queue[bytes | None]
    transport: asyncio.Transport
    client: Client | None

    def __init__(self, factory: "ClientFactory") -> None:
        """Create a ClientProtocol instance."""
        self.factory = factory
        self.client = None
        self.worker_task = None
        self.worker_queue = asyncio.Queue()
        super().__init__()
        # worker_task and transport will be initialized in connection_made.

    # ======== ClientSession implementation
    def kill(self) -> None:
        """Kill this client after 1 second."""

        async def kill() -> None:
            await asyncio.sleep(1)
            self.transport.close()

        mustdone_task_keeper.add(logged_task(asyncio.create_task(kill())))

    def close(self) -> None:
        """Kill the client immediately."""

        self.transport.close()

    def send_packets(self, *packets: ClientBoundPacket) -> None:
        """Send multiple packets."""
        self.send_lines(
            *(packet.pack() for packet in packets), auto_newline=True, together=True
        )

    def get_description(self) -> str:
        """Get text description of this client."""
        if self.client is not None:
            return (
                cast("str", self.transport.get_extra_info("peername")[0])
                + f" ({self.client.callsign.decode(errors='replace')})"
            )

        return cast("str", self.transport.get_extra_info("peername")[0])

    def get_client(self) -> Client | None:
        return self.client

    # ======== asyncio.Protocol implementation
    def line_received(self, line: bytes) -> None:
        """Handle a line."""
        self.worker_queue.put_nowait(line)

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]
        """Initialize something after the connection is made."""
        super().connection_made(transport)
        self.factory.sessions.append(self)
        ip = self.transport.get_extra_info("peername")[0]
        if ip in self.factory.blacklist:
            logger.info("Kicking %s: blacklist", ip)
            self.transport.close()
            return

        self.worker_task = asyncio.create_task(self.handle_line_worker_func())

        def worker_done(task: asyncio.Task) -> None:
            self.worker_task = None
            if task.cancelled():
                return
            exc = task.exception()
            if exc is None:
                return
            logger.error(
                "Worker of %s died unexpectedly",
                self.get_description(),
                exc_info=exc,
            )
            self.send_packets(
                MulticastPacket(
                    FSDClientCommand.MESSAGE,
                    b"server",
                    self.client.callsign if self.client is not None else b"unknown",
                    b"internal server error",
                ),
            )
            self.kill()

        self.worker_task.add_done_callback(worker_done)
        logger.info("New connection from %s.", ip)
        self.factory.plugin_manager.trigger_event_auditers_nonblock(
            "new_connection_established", (self,), {}
        )

    def connection_lost(self, exc: BaseException | None = None) -> None:
        """Handle connection lost."""
        self.factory.sessions.remove(self)
        if self.worker_task:
            self.worker_queue.put_nowait(None)

        client = None
        if self.client is not None:
            self.factory.broadcast(
                RemoveClientPacket(
                    self.client.is_controller,
                    self.client.callsign,
                    self.client.cid.encode(),
                ),
                from_client=self.client,
            )
            del self.factory.clients[self.client.callsign]
            client = self.client
        logger.info(
            "%s disconnected%s.",
            self.get_description(),
            f" due to {exc}" if exc else "",
        )
        self.client = None

        self.factory.plugin_manager.trigger_event_auditers_nonblock(
            "client_disconnected",
            (
                self,
                client,
            ),
            {},
        )

    def buffer_size_exceed(self, length: int) -> None:
        """Called when client exceed max buffer size."""
        logger.info(
            "Kicking %s: buffer size exceeded (%d)",
            self.get_description(),
            length,
        )
        return super().buffer_size_exceed(length)

    # ======== helpers
    def send_error(
        self, errno: FSDClientError, *, env: bytes = b"", fatal: bool = False
    ) -> None:
        """Send an error to client.

        $ERserver:(callsign):(errno):(env):error_text

        Args:
            errno: The error to be sent.
            env: The error env.
            fatal: Disconnect after the error is sent or not.
        """
        self.send_packets(
            ErrorPacket(
                self.client.callsign if self.client is not None else b"unknown",
                errno,
                env,
            )
        )
        if fatal:
            logger.info("Kicking %s: %s", self.get_description(), str(errno))
            self.kill()

    def send_motd(self) -> None:
        """Send motd to client."""
        assert self.client is not None
        self.send_packets(
            MulticastPacket(
                FSDClientCommand.MESSAGE, b"server", self.client.callsign, version_bytes
            ),
            *(
                MulticastPacket(
                    FSDClientCommand.MESSAGE, b"server", self.client.callsign, line
                )
                for line in self.factory.motd
            ),
        )

    def multicast(
        self,
        packet: MulticastPacket,
        custom_at_checker: BroadcastChecker | None = None,
    ) -> bool:
        """Multicast a packet.

        Args:
            packets: The packet to be sent.
            custom_at_checker: Custom checker used when to_limiter is `@`.

        Returns:
            Lines sent to at least client or not.

        Raises:
            NotImplementedError: When an unsupported to_limiter specified.
        """
        assert self.client is not None
        to_limiter = packet.dest
        if to_limiter.startswith(b"*"):
            checker: BroadcastChecker = lambda _, __: True
            if to_limiter == b"*A":
                checker = all_ATC_checker
            elif to_limiter == b"*P":
                checker = all_pilot_checker
            return self.factory.broadcast(
                packet, from_client=self.client, check_func=checker
            )
        if to_limiter.startswith(b"@"):
            return self.factory.broadcast(
                packet,
                from_client=self.client,
                check_func=custom_at_checker
                if custom_at_checker is not None
                else at_checker,
            )
        raise NotImplementedError

    async def check_auth(
        self, cid: bytes, password: bytes, req_rating: int
    ) -> HandleResult:
        """Verify cid & password & rating."""
        try:
            cid_str = cid.decode("utf-8")
            pwd_str = password.decode("utf-8")
        except UnicodeDecodeError:
            self.send_error(FSDClientError.CIDINVALID, env=cid, fatal=True)
            return False, False
        rating = await self.factory.check_auth(cid_str, pwd_str)
        if rating is None:
            self.send_error(FSDClientError.CIDINVALID, env=cid, fatal=True)
            return True, False
        if rating == 0:
            self.send_error(FSDClientError.CSSUSPEND, fatal=True)
            return True, False
        if rating < req_rating:
            self.send_error(
                FSDClientError.LEVEL,
                env=b"%d" % req_rating,
                fatal=True,
            )
            return True, False
        return True, True

    # ======== business logic
    async def handle_line_worker_func(self) -> None:
        """Worker processes line."""
        result: "PyFSDHandledEventResult | PluginHandledEventResult"  # noqa: UP037

        while True:
            try:
                line = await asyncio.wait_for(self.worker_queue.get(), TIMEOUT)
            except asyncio.TimeoutError:
                self.send_line(b"# Timeout")
                await logger.ainfo(f"Kicking {self.get_description()}: timeout")
                self.kill()
                continue

            if line is None:  # sentinel value used in connection_lost()
                break
            if not line:
                continue

            # TODO: currently if the packet cannot be parsed, plugin will not know it.
            # should tweak somehow later
            packet = try_parse(line)
            if not packet:
                self.send_error(FSDClientError.SYNTAX)
                continue

            # First try to let plugins to process
            plugin_result = await self.factory.plugin_manager.trigger_event_handlers(
                "packet_received",
                (self, packet),
                {},
            )
            if plugin_result is None:  # Not handled by plugin
                packet_ok, has_result = await self.handle_packet(packet)
                result = cast(
                    "PyFSDHandledEventResult",
                    {
                        "handled_by_plugin": False,
                        "success": packet_ok and has_result,
                        "packet": packet,
                        "packet_ok": packet_ok,
                        "has_result": has_result,
                    },
                )
            else:
                result = plugin_result

            self.factory.plugin_manager.trigger_event_auditers_nonblock(
                "packet_received",
                (self, packet, result),
                {},
            )

        self.worker_task = None

    @check_packet()
    async def handle_cast(
        self,
        packet: MulticastPacket,
    ) -> HandleResult:
        """Handle a multicast or unicast request."""
        assert self.client is not None

        # to simulate a FSD quirk
        to_packet = (
            dataclasses.replace(packet, data=b"") if packet.data is None else packet
        )
        if packet.dest.startswith(b"*") or packet.dest.startswith(b"@"):  # multicast
            if packet.can_multicast():
                return True, self.multicast(
                    to_packet,
                    custom_at_checker=broadcast_message_checker
                    if packet.command is FSDClientCommand.MESSAGE
                    else None,
                )
            # Not allowed to multicast, so packet_ok is False
            return False, False
        return True, self.factory.send_to(
            to_packet.dest,
            to_packet,
        )

    async def handle_add_client(
        self, packet: AddATCPacket | AddPilotPacket
    ) -> HandleResult:
        """Handle add client request."""
        if self.client is not None:
            self.send_error(FSDClientError.REGISTERED)
            return False, False
        if not is_callsign_valid(packet.source):
            self.send_error(FSDClientError.CSINVALID, fatal=True)
            return False, False
        if packet.protocol != 9:
            self.send_error(FSDClientError.REVISION, fatal=True)
            return False, False
        if packet.source in self.factory.clients:
            self.send_error(FSDClientError.CSINUSE, fatal=True)
            return True, False
        assert packet.password is not None
        if not (
            result := await self.check_auth(packet.cid, packet.password, packet.rating)
        )[1]:
            return result
        is_controller = packet.COMMAND is FSDClientCommand.ADD_ATC
        client = Client(
            is_controller,
            packet.source,
            packet.rating,
            packet.cid.decode("utf-8"),
            packet.protocol,
            packet.realname,
            getattr(packet, "simtype", -1),
            self,
        )
        self.factory.clients[packet.source] = client
        self.client = client
        self.factory.broadcast(
            dataclasses.replace(packet, password=None), from_client=client
        )
        self.send_motd()
        await logger.ainfo(f"New client {self.get_description()}.")
        self.factory.plugin_manager.trigger_event_auditers_nonblock(
            "new_client_created", (self.client,), {}
        )
        return True, True

    @check_packet()
    async def handle_remove_client(self, _: RemoveClientPacket) -> HandleResult:
        """Handle remove client request."""
        assert self.client is not None
        await logger.ainfo("Kicking %s: client asked to remove", self.get_description())
        self.kill()
        return True, True

    @check_packet()
    async def handle_plan(self, packet: FlightPlanPacket) -> HandleResult:
        """Handle plan update request."""
        assert self.client is not None
        self.client.update_plan(
            packet.type,
            packet.aircraft,
            packet.tascruise,
            packet.depairport,
            packet.deptime,
            packet.actdeptime,
            packet.alt,
            packet.destairport,
            packet.hrsenroute,
            packet.minenroute,
            packet.hrsfuel,
            packet.minfuel,
            packet.altairport,
            packet.remarks,
            packet.route,
        )
        self.factory.broadcast(
            dataclasses.replace(packet, dest=b"*A"),
            check_func=broadcast_checkers(
                all_ATC_checker, create_broadcast_range_checker(400)
            ),
            from_client=self.client,
        )
        return True, True

    @check_packet()
    async def handle_pilot_position_update(
        self,
        packet: PilotPositionPacket,
    ) -> HandleResult:
        """Handle pilot position update request."""
        assert self.client is not None
        if not (-90 <= packet.lat <= 90 and -180 <= packet.lon <= 180):
            await logger.adebug(
                "Got invalid position (%f, %f) from %s",
                packet.lat,
                packet.lon,
                self.get_description(),
            )
        self.client.update_pilot_position(
            packet.ident_mode,
            packet.squawk,
            packet.lat,
            packet.lon,
            packet.altitude,
            packet.groundspeed,
            packet.pbh,
            packet.flags,
        )
        self.factory.broadcast(
            dataclasses.replace(packet, rating=self.client.rating),
            check_func=broadcast_position_checker,
            from_client=self.client,
        )
        return True, True

    @check_packet()
    async def handle_ATC_position_update(
        self,
        packet: ATCPositionPacket,
    ) -> HandleResult:
        """Handle ATC position update request."""
        assert self.client is not None
        if not (-90 <= packet.lat <= 90 and -180 <= packet.lon <= 180):
            await logger.adebug(
                "Got invalid position (%f, %f) from %s",
                packet.lat,
                packet.lon,
                self.get_description(),
            )
        self.client.update_ATC_position(
            packet.frequency,
            packet.facility,
            packet.visualrange,
            packet.lat,
            packet.lon,
            packet.altitude,
        )
        self.factory.broadcast(
            dataclasses.replace(packet, rating=self.client.rating),
            check_func=broadcast_position_checker,
            from_client=self.client,
        )
        return True, True

    @check_packet()
    async def handle_server_ping(self, packet: ServerPingPacket) -> HandleResult:
        """Handle server ping request."""
        assert self.client is not None
        self.send_packets(
            MulticastPacket(
                FSDClientCommand.PONG,
                b"server",
                self.client.callsign,
                packet.data if packet.data is not None else b"",
            )
        )
        return True, True

    @check_packet()
    async def handle_weather(
        self,
        packet: WeatherQueryPacket,
    ) -> HandleResult:
        """Handle weather request."""
        assert self.client is not None
        metar = await self.factory.metar_manager.fetch(
            packet.which.decode("ascii", "ignore")
        )
        if not metar:
            self.send_error(FSDClientError.NOWEATHER, env=packet.which)
            return True, False
        profile = metar.clone()
        profile.fix(self.client.position)

        self.send_packets(
            TempPacket(self.client.callsign, profile.temps, profile.barometer),
            WindPacket(self.client.callsign, profile.winds),
            CloudPacket(
                self.client.callsign, profile.clouds, profile.tstorm, profile.visibility
            ),
        )

        return True, True

    @check_packet()
    async def handle_acars(
        self,
        packet: RequestAcarsPacket,
    ) -> HandleResult:
        """Handle acars request."""
        assert self.client is not None

        if packet.query_type.upper() == b"METAR" and packet.which is not None:
            metar = await self.factory.metar_manager.fetch(
                packet.which.decode(errors="ignore")
            )

            if metar is None:
                self.send_error(FSDClientError.NOWEATHER, env=packet.which)
                return True, False

            self.send_packets(
                ReplyAcarsPacket(
                    self.client.callsign, b"METAR", metar.metar.encode("ascii")
                )
            )
            return True, True
        return True, True  # yep

    @check_packet(check_callsign=False)
    async def handle_server_client_query(
        self, packet: ServerClientQueryPacket
    ) -> HandleResult:
        """Handle $CQ:server request."""
        # Behavior may differ from FSD.
        assert self.client is not None
        if packet.query_type.lower() == b"fp":
            # Get flight plan.
            if packet.who is None:
                self.send_error(FSDClientError.SYNTAX)
                return True, False
            if (client := self.factory.clients.get(packet.who)) is None:
                self.send_error(FSDClientError.NOSUCHCS, env=packet.who)
                return True, False
            if (plan := client.flight_plan) is None:
                self.send_error(FSDClientError.NOFP)
                return True, False
            if not self.client.is_controller:
                return False, False
            self.send_packets(
                FlightPlanPacket.from_flight_plan(
                    packet.who, self.client.callsign, plan
                )
            )
        elif packet.query_type.upper() == b"RN":
            # Now we're going to query SERVER's realname, idk why but original FSD would do this quirk
            callsign = b"SERVER"
            if (client := self.factory.clients.get(callsign)) is not None:
                self.send_packets(
                    MulticastPacket(
                        FSDClientCommand.CLIENT_RESPONSE,
                        callsign,
                        self.client.callsign,
                        b"RN:%s:USER:%d" % (client.realname, client.rating),
                    )
                )

                return True, True
            return True, False
        return True, True

    @check_packet(check_callsign=False)
    async def handle_kill(self, packet: KillPacket) -> HandleResult:
        """Handle kill request."""
        assert self.client is not None
        if packet.who not in self.factory.clients:
            self.send_error(FSDClientError.NOSUCHCS, env=packet.who)
            return True, False
        if self.client.rating < 11:
            self.send_packets(
                MulticastPacket(
                    FSDClientCommand.MESSAGE,
                    b"server",
                    self.client.callsign,
                    b"You are not allowed to kill users!",
                )
            )
            return True, False
        self.send_packets(
            MulticastPacket(
                FSDClientCommand.MESSAGE,
                b"server",
                self.client.callsign,
                b"Attempting to kill %s" % packet.who,
            )
        )
        self.factory.send_to(
            packet.who, KillPacket(b"SERVER", packet.who, packet.reason)
        )
        session_to_kill = self.factory.clients[packet.who].session
        logger.info(
            "Kicking %s: killed by %s",
            session_to_kill.get_description(),
            self.client.callsign.decode(errors="replace"),
        )
        session_to_kill.kill()
        return True, True

    async def handle_packet(
        self,
        packet: ServerBoundPacket,
    ) -> HandleResult:
        """Handle a packet."""
        match packet:
            case AddATCPacket() | AddPilotPacket():
                return await self.handle_add_client(packet)
            case FlightPlanPacket():
                return await self.handle_plan(packet)
            case RemoveClientPacket():
                return await self.handle_remove_client(packet)
            case PilotPositionPacket():
                return await self.handle_pilot_position_update(packet)
            case ATCPositionPacket():
                return await self.handle_ATC_position_update(packet)
            case MulticastPacket():
                return await self.handle_cast(packet)
            case WeatherQueryPacket():
                return await self.handle_weather(packet)
            case RequestAcarsPacket():
                return await self.handle_acars(packet)
            case ServerClientQueryPacket():
                return await self.handle_server_client_query(packet)
            case ServerPingPacket():
                return await self.handle_server_ping(packet)
            case KillPacket():
                return await self.handle_kill(packet)
            case _:
                assert_never(packet)
