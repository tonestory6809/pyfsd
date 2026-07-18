"""FSD protocol 9 packets."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, TypeAlias

from typing_extensions import Self

from pyfsd.metar.profile import CloudLayer, TempLayer, WindLayer

from ..utils import atoi, str_to_float
from . import SPLIT_SIGN, FSDClientCommand
from .errors import FSDClientError

if TYPE_CHECKING:
    from pyfsd.object.client import FlightPlan

__all__ = [
    "ATCPositionPacket",
    "AddATCPacket",
    "AddPilotPacket",
    "ClientBoundPacket",
    "CloudPacket",
    "ErrorPacket",
    "FlightPlanPacket",
    "KillPacket",
    "MulticastPacket",
    "Packet",
    "PilotPositionPacket",
    "RemoveClientPacket",
    "ReplyAcarsPacket",
    "RequestAcarsPacket",
    "ServerBoundPacket",
    "ServerClientQueryPacket",
    "ServerPingPacket",
    "TempPacket",
    "WeatherQueryPacket",
    "WindDeltaPacket",
    "WindPacket",
    "try_parse",
]


class Packet(ABC):
    """A network packet."""

    @abstractmethod
    def pack(self) -> bytes:
        """Pack this packet into bytes."""

    @classmethod
    @abstractmethod
    def unpack(cls, data: bytes) -> Self:
        """Try unpack bytes into the packet."""


@dataclass(slots=True)
class AddATCPacket(Packet):
    """Packet requesting/notifying a new ATC client. Server / client bound.

    Attributes:
        source: Source callsign of the packet.
        protocol: Must be 9.
    """

    COMMAND: ClassVar = FSDClientCommand.ADD_ATC
    REQUIRED_PARTS: ClassVar = 7
    source: bytes
    realname: bytes
    cid: bytes
    password: bytes | None
    rating: int
    protocol: int

    def pack(self) -> bytes:
        if self.password is not None:  # server bound
            return b"%s%s:SERVER:%s:%s:%s:%d:%d" % (
                self.COMMAND,
                self.source,
                self.realname,
                self.cid,
                self.password,
                self.rating,
                self.protocol,
            )
        return b"%s%s:SERVER:%s:%s::%d" % (  # client bound
            self.COMMAND,
            self.source,
            self.realname,
            self.cid,
            self.rating,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        # Not implementing malformed client bound packet parsing here.
        callsign, _, realname, cid, password, rating, protocol, *_ = data[3:].split(
            SPLIT_SIGN, cls.REQUIRED_PARTS
        )
        return cls(
            callsign,
            realname,
            cid,
            password,
            0 if (rating_int := atoi(rating)) < 0 else rating_int,
            atoi(protocol),
        )


@dataclass(slots=True)
class AddPilotPacket(Packet):
    """Packet requesting/notifying a new pilot client. Server / client bound.

    Attributes:
        protocol: Must be 9.
        simtype: Usually used to represent kind of flight simulator.
    """

    COMMAND: ClassVar = FSDClientCommand.ADD_PILOT
    REQUIRED_PARTS: ClassVar = 8
    source: bytes
    cid: bytes
    password: bytes | None
    rating: int
    protocol: int
    simtype: int
    realname: bytes

    def pack(self) -> bytes:
        if self.password is not None:  # server bound
            return b"%s%s:SERVER:%s:%s:%d:%d:%d:%s" % (
                self.COMMAND,
                self.source,
                self.cid,
                self.password,
                self.rating,
                self.protocol,
                self.simtype,
                self.realname,
            )
        # FSD 9 fucked up with sprintf, that's the behaviour on glibc system
        return b"%s%s:SERVER:%s::%d:%d:%d" % (  # client bound
            self.COMMAND,
            self.source,
            self.cid,
            self.rating,
            self.rating,
            self.simtype,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        # FSD 9 protocol explicitly allows extra fields. So if there're 8 required parts,
        # we cut a maximum of 8 times (so we get maximum 9 parts) and discard the last
        # extra part, if there're.
        callsign, _, cid, password, rating, protocol, simtype, realname, *_ = data[
            3:
        ].split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(
            callsign,
            cid,
            password,
            0 if (rating_int := atoi(rating)) < 0 else rating_int,
            atoi(protocol),
            atoi(simtype),
            realname,
        )


@dataclass(slots=True)
class FlightPlanPacket(Packet):
    """Packet posting/notifying a new flight plan. Server / client bound.

    Attributes:
        dest: The expected receiver of the flight plan.
        type: Flight rules. b"I" => IFR, b"V" => VFR.
        aircraft: Aircraft ICAO.
        tascruise: True cruising speed.
        depairport: Departure airport.
        deptime: Estimated departure time.
        actdeptime: Actually departure time.
        alt: Cruising altitude.
        destairport: Arrival airport.
        hrsenroute: Hours enroute.
        minenroute: Minutes enroute.
        hrsfuel: Hours fuel available.
        minfuel: Minutes fuel available.
        altairport: Alternative arrival airport.
        remarks: Just remarks.
        route: Flight airway.
    """

    COMMAND: ClassVar = FSDClientCommand.PLAN
    REQUIRED_PARTS: ClassVar = 17
    source: bytes
    dest: bytes
    type: bytes
    aircraft: bytes
    tascruise: int
    depairport: bytes
    deptime: int
    actdeptime: int
    alt: bytes
    destairport: bytes
    hrsenroute: int
    minenroute: int
    hrsfuel: int
    minfuel: int
    altairport: bytes
    remarks: bytes
    route: bytes

    def pack(self) -> bytes:
        return b"%s%s:%s:%s:%s:%d:%s:%d:%d:%s:%s:%d:%d:%d:%d:%s:%s:%s" % (
            self.COMMAND,
            self.source,
            self.dest,
            self.type,
            self.aircraft,
            self.tascruise,
            self.depairport,
            self.deptime,
            self.actdeptime,
            self.alt,
            self.destairport,
            self.hrsenroute,
            self.minenroute,
            self.hrsfuel,
            self.minfuel,
            self.altairport,
            self.remarks,
            self.route,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        (
            callsign,
            dest,
            typ,
            aircraft,
            tascruise,
            depairport,
            deptime,
            actdeptime,
            alt,
            destairport,
            hrsenroute,
            minenroute,
            hrsfuel,
            minfuel,
            altairport,
            remarks,
            route,
            *_,
        ) = data[3:].split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(
            callsign,
            dest,
            typ[:1],
            aircraft,
            atoi(tascruise),
            depairport,
            atoi(deptime),
            atoi(actdeptime),
            alt,
            destairport,
            atoi(hrsenroute),
            atoi(minenroute),
            atoi(hrsfuel),
            atoi(minfuel),
            altairport,
            remarks,
            route,
        )

    @classmethod
    def from_flight_plan(cls, source: bytes, dest: bytes, plan: "FlightPlan") -> Self:
        return cls(
            source,
            dest,
            plan.type,
            plan.aircraft,
            plan.tascruise,
            plan.dep_airport,
            plan.dep_time,
            plan.act_dep_time,
            plan.alt,
            plan.dest_airport,
            plan.hrs_enroute,
            plan.min_enroute,
            plan.hrs_fuel,
            plan.min_fuel,
            plan.alt_airport,
            plan.remarks,
            plan.route,
        )


@dataclass(slots=True)
class RemoveClientPacket(Packet):
    """Packet requesting/notifying logoff of a client. Server / client bound.

    Attributes:
        cid: CID of the client being logged off. Not required on server bound.
    """

    COMMANDS: ClassVar = (FSDClientCommand.REMOVE_ATC, FSDClientCommand.REMOVE_PILOT)
    REQUIRED_PARTS: ClassVar = 1
    is_controller: bool
    source: bytes
    cid: bytes | None

    def pack(self) -> bytes:
        if self.cid is not None:
            return b"%s%s:%s" % (
                FSDClientCommand.REMOVE_ATC
                if self.is_controller
                else FSDClientCommand.REMOVE_PILOT,
                self.source,
                self.cid,
            )
        return (
            FSDClientCommand.REMOVE_ATC
            if self.is_controller
            else FSDClientCommand.REMOVE_PILOT
        ) + self.source

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        cmd_callsign, *extra = data.split(SPLIT_SIGN, cls.REQUIRED_PARTS + 1)
        if cmd_callsign.startswith(FSDClientCommand.REMOVE_ATC):
            is_controller = True
        elif cmd_callsign.startswith(FSDClientCommand.REMOVE_PILOT):
            is_controller = False
        else:
            raise ValueError("not a RemoveClientPacket")
        return cls(is_controller, cmd_callsign[3:], extra[0] if extra else None)


@dataclass(slots=True)
class PilotPositionPacket(Packet):
    """Packet posting/notifying an updated position of a pilot. Server / client bound.

    Attributes:
        ident_mode: Mode of the transponder.
            Standby => b"S", ident => b"Y", else b"N".
        pbh: Pitch, banking and heading.
            https://github.com/swift-project/pilotclient/blob/main/src/core/fsd/pbh.h#L37-L76
        flags: Usually pressure altitude minus true altitude.
    """

    COMMAND: ClassVar = FSDClientCommand.PILOT_POSITION
    REQUIRED_PARTS: ClassVar = 10
    ident_mode: bytes
    source: bytes
    squawk: int
    rating: int
    lat: float
    lon: float
    altitude: int
    groundspeed: int
    pbh: int
    flags: int

    def pack(self) -> bytes:
        return b"%s%s:%s:%d:%d:%.5f:%.5f:%d:%d:%d:%d" % (
            self.COMMAND,
            self.ident_mode,
            self.source,
            self.squawk,
            self.rating,
            self.lat,
            self.lon,
            self.altitude,
            self.groundspeed,
            self.pbh,
            self.flags,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        (
            ident_mode,
            callsign,
            squawk,
            rating,
            lat,
            lon,
            altitude,
            groundspeed,
            pbh,
            flags,
            *_,
        ) = data[1:].split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        # TODO: str_to_float works differently from strtod. haven't find an efficient
        # impl yet, so hopefully users won't pass weird double that float cannot handle
        return cls(
            ident_mode,
            callsign,
            atoi(squawk),
            atoi(rating),
            str_to_float(lat),
            str_to_float(lon),
            atoi(altitude),
            atoi(groundspeed),
            # there's actually a overflow here not simulated
            atoi(pbh) & 0xFFFFFFFF,  # unsigned
            atoi(flags),
        )


@dataclass(slots=True)
class ATCPositionPacket(Packet):
    """Packet posting/notifying an updated position of a ATC. Server / client bound.

    Attributes:
        facility: Facility level of the ATC.
            https://github.com/renorris/openfsd/blob/main/docs/enumerations.md#facility-types
        visualrange: Visual range in nautical miles.
    """

    COMMAND: ClassVar = FSDClientCommand.ATC_POSITION
    REQUIRED_PARTS: ClassVar = 8
    source: bytes
    frequency: int
    facility: int
    visualrange: int
    rating: int
    lat: float
    lon: float
    altitude: int

    def pack(self) -> bytes:
        return b"%s%s:%d:%d:%d:%d:%.5f:%.5f:%d" % (
            self.COMMAND,
            self.source,
            self.frequency,
            self.facility,
            self.visualrange,
            self.rating,
            self.lat,
            self.lon,
            self.altitude,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        (callsign, frequency, facility, visualrange, rating, lat, lon, altitude, *_) = (
            data[1:].split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        )
        return cls(
            callsign,
            atoi(frequency),
            atoi(facility),
            atoi(visualrange),
            atoi(rating),
            str_to_float(lat),
            str_to_float(lon),
            atoi(altitude),
        )


@dataclass(slots=True)
class MulticastPacket(Packet):
    """Packet that's simply being sent to 1 or multiple target. Server / client bound.

    Attributes:
        dest: Destination of the packet. Some special case were present:
          b"*A" => All ATCs, b"*P" => All pilots,
          starts with b"@" => Clients in range, starts with b"*" => Everyone
    """

    COMMANDS: ClassVar = (
        FSDClientCommand.PONG,
        FSDClientCommand.PING,
        FSDClientCommand.MESSAGE,
        FSDClientCommand.REQUEST_HANDOFF,
        FSDClientCommand.ACCEPT_HANDOFF,
        FSDClientCommand.SQUAWK_BOX,
        FSDClientCommand.PRO_CONTROLLER,
        FSDClientCommand.REQUEST_COMM,
        FSDClientCommand.REPLY_COMM,
        FSDClientCommand.CLIENT_RESPONSE,
        FSDClientCommand.CLIENT_QUERY,
    )
    REQUIRED_PARTS: ClassVar = {
        FSDClientCommand.PONG: 2,
        FSDClientCommand.PING: 2,
        FSDClientCommand.MESSAGE: 3,
        FSDClientCommand.REQUEST_HANDOFF: 3,
        FSDClientCommand.ACCEPT_HANDOFF: 3,
        FSDClientCommand.SQUAWK_BOX: 2,
        FSDClientCommand.PRO_CONTROLLER: 3,
        FSDClientCommand.REQUEST_COMM: 2,
        FSDClientCommand.REPLY_COMM: 3,
        FSDClientCommand.CLIENT_RESPONSE: 4,
        FSDClientCommand.CLIENT_QUERY: 3,
    }
    command: FSDClientCommand
    source: bytes
    dest: bytes
    data: bytes | None

    def pack(self) -> bytes:
        if self.data:
            return b"%s%s:%s:%s" % (self.command, self.source, self.dest, self.data)
        return b"%s%s:%s" % (self.command, self.source, self.dest)

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        cmd_callsign, dest, *extra = data.split(SPLIT_SIGN, 2)
        for possible_command in cls.COMMANDS:
            if cmd_callsign.startswith(possible_command):
                return cls(
                    possible_command,
                    cmd_callsign[3:],
                    dest,
                    extra[0] if extra else None,
                )
        raise ValueError("not a MulticastPacket")

    def can_multicast(self) -> bool:
        """Some packets can be sent to multiple dest, some not."""
        return self.command in (
            FSDClientCommand.CLIENT_QUERY,
            FSDClientCommand.MESSAGE,
            FSDClientCommand.PING,
            FSDClientCommand.PONG,
        )


@dataclass(slots=True)
class WeatherQueryPacket(Packet):
    """Packet that requires weather information. Server bound.

    Attributes:
        which: The airport ICAO.
    """

    COMMAND: ClassVar = FSDClientCommand.WEATHER
    REQUIRED_PARTS: ClassVar = 3
    source: bytes
    which: bytes

    def pack(self) -> bytes:
        return b"%s%s:SERVER:%s" % (self.COMMAND, self.source, self.which)

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        callsign, _, which, *_ = data[3:].split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(callsign, which)


@dataclass(slots=True)
class RequestAcarsPacket(Packet):
    """Packet that requests ACARS (usually METAR). Server bound.

    Attributes:
        query_type: Case-insensitively b"METAR" for METAR request.
        which: The airport ICAO if is METAR request.
    """

    COMMAND: ClassVar = FSDClientCommand.REQUEST_ACARS
    REQUIRED_PARTS: ClassVar = 3
    source: bytes
    query_type: bytes
    which: bytes | None

    def pack(self) -> bytes:
        if self.which is None:
            return b"%s%s:SERVER:%s" % (self.COMMAND, self.source, self.query_type)
        return b"%s%s:SERVER:%s:%s" % (
            self.COMMAND,
            self.source,
            self.query_type,
            self.which,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        callsign, _, query_type, *extra = data[3:].split(
            SPLIT_SIGN, cls.REQUIRED_PARTS + 1
        )
        return cls(callsign, query_type, extra[0] if extra else None)


@dataclass(slots=True)
class ServerPingPacket(Packet):
    """Packet that pings server. Server bound."""

    COMMAND: ClassVar = FSDClientCommand.PING
    REQUIRED_PARTS: ClassVar = 2
    source: bytes
    data: bytes | None

    def pack(self) -> bytes:
        if self.data:
            return b"%s%s:SERVER:%s" % (self.COMMAND, self.source, self.data)
        return b"%s%s:SERVER" % (self.COMMAND, self.source)

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        callsign, _, *extra = data[3:].split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(callsign, extra[0] if extra else None)


@dataclass(slots=True)
class ServerClientQueryPacket(Packet):
    """Packet that requests others' information. Server bound.

    Attributes:
        query_type: Case-insensitively b"FP" for flight plan request.
            might also be b"RN" for realname, but FSD 9 fucked up by treating packet[1]
            as others' callsign, which is always b"SERVER" (also case insensitively)
        who: Others' callsign if is flight plan request.
    """

    COMMAND: ClassVar = FSDClientCommand.CLIENT_QUERY
    REQUIRED_PARTS: ClassVar = 3
    source: bytes
    query_type: bytes
    who: bytes | None

    def pack(self) -> bytes:
        if self.who is None:
            return b"%s%s:SERVER:%s" % (self.COMMAND, self.source, self.query_type)
        return b"%s%s:SERVER:%s:%s" % (
            self.COMMAND,
            self.source,
            self.query_type,
            self.who,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        callsign, _, query_type, *extra = data[3:].split(
            SPLIT_SIGN, cls.REQUIRED_PARTS + 1
        )
        return cls(callsign, query_type, extra[0] if extra else None)


@dataclass(slots=True)
class KillPacket(Packet):
    """Packet that requesting/notifying the removal of others from the server. Server/client bound."""

    COMMAND: ClassVar = FSDClientCommand.KILL
    REQUIRED_PARTS: ClassVar = 3
    source: bytes
    who: bytes
    reason: bytes

    def pack(self) -> bytes:
        return b"%s%s:%s:%s" % (self.COMMAND, self.source, self.who, self.reason)

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        callsign, who, reason, *_ = data[3:].split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(callsign, who, reason)


@dataclass(slots=True)
class WindDeltaPacket(Packet):
    """Packet that alike heartbeat (related to wind?). Client bound."""

    COMMAND: ClassVar = FSDClientCommand.WIND_DELTA
    REQUIRED_PARTS: ClassVar = 4
    dest: bytes
    speed: int
    direction: int

    def pack(self) -> bytes:
        return b"%sSERVER:%s:%d:%d" % (
            self.COMMAND,
            self.dest,
            self.speed,
            self.direction,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        _, dest, speed, direction, *_ = data.split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(dest, atoi(speed), atoi(direction))


@dataclass(slots=True)
class ErrorPacket(Packet):
    """Packet that reports error. Client bound."""

    COMMAND: ClassVar = FSDClientCommand.ERROR
    REQUIRED_PARTS: ClassVar = 5
    dest: bytes
    error: FSDClientError
    env: bytes
    error_str: bytes | None = field(default=None)

    def pack(self) -> bytes:
        return b"%sserver:%s:%03d:%s:%s" % (
            self.COMMAND,
            self.dest,
            self.error,
            self.env,
            bytes(self.error) if self.error_str is None else self.error_str,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        _, dest, errno, env, errstr = data.split(SPLIT_SIGN, 4)
        return cls(dest, FSDClientError(atoi(errno)), env, errstr)


@dataclass(slots=True)
class TempPacket(Packet):
    """Packet that describes temperature. Client bound."""

    COMMAND: ClassVar = FSDClientCommand.TEMP_DATA
    REQUIRED_PARTS: ClassVar = 11
    dest: bytes
    layers: tuple[TempLayer, TempLayer, TempLayer, TempLayer]
    barometer: int

    def pack(self) -> bytes:
        return b"%sserver:%s:%d:%d:%d:%d:%d:%d:%d:%d:%d" % (
            self.COMMAND,
            self.dest,
            self.layers[0].ceiling,
            self.layers[0].temp,
            self.layers[1].ceiling,
            self.layers[1].temp,
            self.layers[2].ceiling,
            self.layers[2].temp,
            self.layers[3].ceiling,
            self.layers[3].temp,
            self.barometer,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        _, dest, c0, t0, c1, t1, c2, t2, c3, t3, barometer, *_ = data.split(
            SPLIT_SIGN, cls.REQUIRED_PARTS
        )
        return cls(
            dest,
            (
                TempLayer(atoi(c0), atoi(t0)),
                TempLayer(atoi(c1), atoi(t1)),
                TempLayer(atoi(c2), atoi(t2)),
                TempLayer(atoi(c3), atoi(t3)),
            ),
            atoi(barometer),
        )


@dataclass(slots=True)
class WindPacket(Packet):
    """Packet that describes wind. Client bound."""

    COMMAND: ClassVar = FSDClientCommand.WIND_DATA
    REQUIRED_PARTS: ClassVar = 26
    dest: bytes
    layers: tuple[WindLayer, WindLayer, WindLayer, WindLayer]

    def pack(self) -> bytes:
        return (
            b"%sserver:%s:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d"
            % (
                self.COMMAND,
                self.dest,
                self.layers[0].ceiling,
                self.layers[0].floor,
                self.layers[0].direction,
                self.layers[0].speed,
                self.layers[0].gusting,
                self.layers[0].turbulence,
                self.layers[1].ceiling,
                self.layers[1].floor,
                self.layers[1].direction,
                self.layers[1].speed,
                self.layers[1].gusting,
                self.layers[1].turbulence,
                self.layers[2].ceiling,
                self.layers[2].floor,
                self.layers[2].direction,
                self.layers[2].speed,
                self.layers[2].gusting,
                self.layers[2].turbulence,
                self.layers[3].ceiling,
                self.layers[3].floor,
                self.layers[3].direction,
                self.layers[3].speed,
                self.layers[3].gusting,
                self.layers[3].turbulence,
            )
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        (
            _,
            dest,
            c0,
            f0,
            d0,
            s0,
            g0,
            t0,
            c1,
            f1,
            d1,
            s1,
            g1,
            t1,
            c2,
            f2,
            d2,
            s2,
            g2,
            t2,
            c3,
            f3,
            d3,
            s3,
            g3,
            t3,
            *_,
        ) = data.split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(
            dest,
            (
                WindLayer(atoi(c0), atoi(f0), atoi(d0), atoi(s0), atoi(g0), atoi(t0)),
                WindLayer(atoi(c1), atoi(f1), atoi(d1), atoi(s1), atoi(g1), atoi(t1)),
                WindLayer(atoi(c2), atoi(f2), atoi(d2), atoi(s2), atoi(g2), atoi(t2)),
                WindLayer(atoi(c3), atoi(f3), atoi(d3), atoi(s3), atoi(g3), atoi(t3)),
            ),
        )


@dataclass(slots=True)
class CloudPacket(Packet):
    """Packet that describes cloud. Client bound."""

    COMMAND: ClassVar = FSDClientCommand.CLOUD_DATA
    REQUIRED_PARTS: ClassVar = 18
    dest: bytes
    layers: tuple[CloudLayer, CloudLayer]
    tstorm: CloudLayer
    visibility: float

    def pack(self) -> bytes:
        return b"%sserver:%s:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%.2f" % (
            self.COMMAND,
            self.dest,
            self.layers[0].ceiling,
            self.layers[0].floor,
            self.layers[0].coverage,
            self.layers[0].icing,
            self.layers[0].turbulence,
            self.layers[1].ceiling,
            self.layers[1].floor,
            self.layers[1].coverage,
            self.layers[1].icing,
            self.layers[1].turbulence,
            self.tstorm.ceiling,
            self.tstorm.floor,
            self.tstorm.coverage,
            self.tstorm.icing,
            self.tstorm.turbulence,
            self.visibility,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        (
            _,
            dest,
            ceil0,
            f0,
            cov0,
            i0,
            t0,
            ceil1,
            f1,
            cov1,
            i1,
            t1,
            ceil2,
            f2,
            cov2,
            i2,
            t2,
            vis,
            *_,
        ) = data.split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(
            dest,
            (
                CloudLayer(atoi(ceil0), atoi(f0), atoi(cov0), atoi(i0), atoi(t0)),
                CloudLayer(atoi(ceil1), atoi(f1), atoi(cov1), atoi(i1), atoi(t1)),
            ),
            CloudLayer(atoi(ceil2), atoi(f2), atoi(cov2), atoi(i2), atoi(t2)),
            str_to_float(vis),
        )


@dataclass(slots=True)
class ReplyAcarsPacket(Packet):
    """Packet that replies to ACARS (normally METAR) request. Client bound.

    Attributes:
        reply_type: b"METAR" for METAR reply.
    """

    COMMAND: ClassVar = FSDClientCommand.REPLY_ACARS
    REQUIRED_PARTS: ClassVar = 4
    dest: bytes
    reply_type: bytes
    data: bytes

    def pack(self) -> bytes:
        return b"%sserver:%s:%s:%s" % (
            self.COMMAND,
            self.dest,
            self.reply_type,
            self.data,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Self:
        _, callsign, reply_type, data, *_ = data.split(SPLIT_SIGN, cls.REQUIRED_PARTS)
        return cls(callsign, reply_type, data)


ServerBoundPacket: TypeAlias = (
    AddATCPacket
    | AddPilotPacket
    | FlightPlanPacket
    | RemoveClientPacket
    | PilotPositionPacket
    | ATCPositionPacket
    | MulticastPacket
    | WeatherQueryPacket
    | RequestAcarsPacket
    | ServerClientQueryPacket
    | ServerPingPacket
    | KillPacket
)

ClientBoundPacket: TypeAlias = (
    AddATCPacket
    | AddPilotPacket
    | FlightPlanPacket
    | RemoveClientPacket
    | PilotPositionPacket
    | ATCPositionPacket
    | MulticastPacket
    | KillPacket
    | WindDeltaPacket
    | ErrorPacket
    | TempPacket
    | WindPacket
    | CloudPacket
    | ReplyAcarsPacket
)


def try_parse(data: bytes) -> ServerBoundPacket | None:
    """Try to parse raw pdu into packet."""
    parts = data.count(b":") + 1
    for possible_pos_packet in (
        PilotPositionPacket,
        ATCPositionPacket,
    ):
        if (
            data.startswith(possible_pos_packet.COMMAND)
            and parts >= possible_pos_packet.REQUIRED_PARTS
        ):
            return possible_pos_packet.unpack(data)
    for possible_command in MulticastPacket.COMMANDS:
        if (
            data.startswith(possible_command)
            and parts >= MulticastPacket.REQUIRED_PARTS[possible_command]
        ):
            packet = MulticastPacket.unpack(data)
            if (
                packet.command is FSDClientCommand.PING
                and packet.dest.upper() == b"SERVER"
            ):
                return ServerPingPacket(packet.source, packet.data)
            if (
                packet.command is FSDClientCommand.CLIENT_QUERY
                and packet.dest.upper() == b"SERVER"
            ):
                if packet.data is None:
                    return None
                query_type, *extra = packet.data.split(SPLIT_SIGN, 2)
                return ServerClientQueryPacket(
                    packet.source, query_type, extra[0] if extra else None
                )
            return packet
    for possible_packet in (
        FlightPlanPacket,
        WeatherQueryPacket,
        RequestAcarsPacket,
        KillPacket,
        AddATCPacket,
        AddPilotPacket,
    ):
        if (
            data.startswith(possible_packet.COMMAND)
            and parts >= possible_packet.REQUIRED_PARTS
        ):
            return possible_packet.unpack(data)
    for possible_command in RemoveClientPacket.COMMANDS:
        if (
            data.startswith(possible_command)
            and parts >= RemoveClientPacket.REQUIRED_PARTS
        ):
            return RemoveClientPacket.unpack(data)
    return None
