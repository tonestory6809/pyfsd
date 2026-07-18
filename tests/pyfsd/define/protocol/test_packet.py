"""This module tests pyfsd.define.protocol.packet."""

from unittest import TestCase

from pyfsd.client.object import FlightPlan
from pyfsd.define.protocol import FSDClientCommand
from pyfsd.define.protocol.errors import FSDClientError
from pyfsd.define.protocol.packet import (
    AddATCPacket,
    AddPilotPacket,
    ATCPositionPacket,
    CloudPacket,
    ErrorPacket,
    FlightPlanPacket,
    KillPacket,
    MulticastPacket,
    PilotPositionPacket,
    RemoveClientPacket,
    ReplyAcarsPacket,
    RequestAcarsPacket,
    ServerClientQueryPacket,
    ServerPingPacket,
    TempPacket,
    WeatherQueryPacket,
    WindDeltaPacket,
    WindPacket,
    try_parse,
)
from pyfsd.metar.profile import CloudLayer, TempLayer, WindLayer


class TestPacket(TestCase):
    """Test if pyfsd.define.protocol.packet works."""

    def test_AddATCPacket(self) -> None:
        packet = AddATCPacket(b"source", b"realname", b"cid", b"password", 0, 1)
        packed = b"#AAsource:SERVER:realname:cid:password:0:1"
        self.assertEqual(packed, packet.pack())
        # FSD 9 protocol explicitly allows extra fields, so applying some extra parts to test it
        self.assertEqual(AddATCPacket.unpack(packed + b":1:2:3"), packet)
        packet = AddATCPacket(b"source", b"realname", b"cid", None, 0, 1)
        packed = b"#AAsource:SERVER:realname:cid::0"
        self.assertEqual(packed, packet.pack())
        # self.assertEqual(AddATCPacket.unpack(packed), packet)

    def test_AddPilotPacket(self) -> None:
        packet = AddPilotPacket(b"source", b"cid", b"password", 0, 1, 2, b"realname")
        packed = b"#APsource:SERVER:cid:password:0:1:2:realname"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(AddPilotPacket.unpack(packed + b":1:2:3"), packet)
        packet = AddPilotPacket(b"source", b"cid", None, 0, 1, 2, b"realname")
        packed = b"#APsource:SERVER:cid::0:0:2"
        self.assertEqual(packed, packet.pack())
        # self.assertEqual(AddATCPacket.unpack(packed), packet)

    def test_FlightPlanPacket(self) -> None:
        plan = FlightPlan(
            0,
            b"I",
            b"aircraft",
            0,
            b"depairport",
            1,
            2,
            b"alt",
            b"destairport",
            3,
            4,
            5,
            6,
            b"altairport",
            b"remarks",
            b"route",
        )
        packet = FlightPlanPacket(
            b"source",
            b"dest",
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
        packed = b"$FPsource:dest:I:aircraft:0:depairport:1:2:alt:destairport:3:4:5:6:altairport:remarks:route"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(FlightPlanPacket.unpack(packed + b":1:2:3"), packet)
        self.assertEqual(
            FlightPlanPacket.from_flight_plan(b"source", b"dest", plan), packet
        )

    def test_RemoveClientPacket(self) -> None:
        cases = (
            (True, b"cid", b"#DAsource:cid"),
            (True, None, b"#DAsource"),
            (False, b"cid", b"#DPsource:cid"),
            (False, None, b"#DPsource"),
        )
        for is_controller, cid, packed in cases:
            with self.subTest(is_controller=is_controller, has_cid=cid is None):
                packet = RemoveClientPacket(is_controller, b"source", cid)
                self.assertEqual(packed, packet.pack())
                self.assertEqual(RemoveClientPacket.unpack(packed), packet)
                if cid is not None:
                    self.assertEqual(
                        RemoveClientPacket.unpack(packed + b":1:2:3"), packet
                    )

    def test_PilotPositionPacket(self) -> None:
        packet = PilotPositionPacket(b"N", b"source", 0, 1, 2, 3, 4, 5, 6, 7)
        packed = b"@N:source:0:1:2.00000:3.00000:4:5:6:7"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(PilotPositionPacket.unpack(packed + b":1:2:3"), packet)

    def test_ATCPositionPacket(self) -> None:
        packet = ATCPositionPacket(b"source", 0, 1, 2, 3, 4, 5, 6)
        packed = b"%source:0:1:2:3:4.00000:5.00000:6"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(ATCPositionPacket.unpack(packed + b":1:2:3"), packet)

    def test_MulticastPacket(self) -> None:
        packet = MulticastPacket(
            FSDClientCommand.MESSAGE, b"source", b"dest", b"data:6666"
        )
        packed = b"#TMsource:dest:data:6666"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(MulticastPacket.unpack(packed), packet)
        assert packet.can_multicast()
        packet = MulticastPacket(
            FSDClientCommand.REQUEST_HANDOFF, b"source", b"dest", None
        )
        packed = b"$HOsource:dest"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(MulticastPacket.unpack(packed), packet)
        assert not packet.can_multicast()
        with self.assertRaises(ValueError):
            MulticastPacket.unpack(b"#AP:")
        # This packet allows infinite fields, check if they're parsed properly
        self.assertEqual(
            MulticastPacket.unpack(b"#TM" + b":" * 100).pack().count(b":"), 100
        )

    def test_WeatherQueryPacket(self) -> None:
        packet = WeatherQueryPacket(b"source", b"which")
        packed = b"#WXsource:SERVER:which"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(WeatherQueryPacket.unpack(packed + b":1:2:3"), packet)

    def test_RequestAcarsPacket(self) -> None:
        packet = RequestAcarsPacket(b"source", b"type", b"which")
        packed = b"$AXsource:SERVER:type:which"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(RequestAcarsPacket.unpack(packed + b":1:2:3"), packet)
        packet = RequestAcarsPacket(b"source", b"type", None)
        packed = b"$AXsource:SERVER:type"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(RequestAcarsPacket.unpack(packed), packet)

    def test_ServerPingPacket(self) -> None:
        packet = ServerPingPacket(b"source", b"data")
        packed = b"$PIsource:SERVER:data"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(ServerPingPacket.unpack(packed), packet)
        packet = ServerPingPacket(b"source", None)
        packed = b"$PIsource:SERVER"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(ServerPingPacket.unpack(packed), packet)
        # This packet allows infinite fields, check if they're parsed properly
        self.assertEqual(
            ServerPingPacket.unpack(b"#TM" + b":" * 100).pack().count(b":"), 100
        )

    def test_ServerClientQueryPacket(self) -> None:
        packet = ServerClientQueryPacket(b"source", b"type", b"who")
        packed = b"$CQsource:SERVER:type:who"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(ServerClientQueryPacket.unpack(packed + b":1:2:3"), packet)
        packet = ServerClientQueryPacket(b"source", b"type", None)
        packed = b"$CQsource:SERVER:type"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(ServerClientQueryPacket.unpack(packed), packet)

    def test_KillPacket(self) -> None:
        packet = KillPacket(b"source", b"who", b"reason")
        packed = b"$!!source:who:reason"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(KillPacket.unpack(packed + b":1:2:3"), packet)

    def test_WindDeltaPacket(self) -> None:
        packet = WindDeltaPacket(b"dest", 0, 1)
        packed = b"#DLSERVER:dest:0:1"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(WindDeltaPacket.unpack(packed + b":1:2:3"), packet)

    def test_ErrorPacket(self) -> None:
        packet = ErrorPacket(b"dest", FSDClientError.OK, b"env", b"error:666")
        packed = b"$ERserver:dest:000:env:error:666"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(ErrorPacket.unpack(packed), packet)
        packet = ErrorPacket(b"dest", FSDClientError.OK, b"env", None)
        packed = b"$ERserver:dest:000:env:No error"
        self.assertEqual(packed, packet.pack())
        # self.assertEqual(ErrorPacket.unpack(packed), packet)

    def test_TempPacket(self) -> None:
        packet = TempPacket(
            b"dest",
            (TempLayer(0, 1), TempLayer(2, 3), TempLayer(4, 5), TempLayer(6, 7)),
            8,
        )
        packed = b"#TDserver:dest:0:1:2:3:4:5:6:7:8"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(TempPacket.unpack(packed + b":1:2:3"), packet)

    def test_WindPacket(self) -> None:
        packet = WindPacket(
            b"dest",
            (
                WindLayer(0, 1, 2, 3, 4, 5),
                WindLayer(6, 7, 8, 9, 10, 11),
                WindLayer(12, 13, 14, 15, 16, 17),
                WindLayer(18, 19, 20, 21, 22, 23),
            ),
        )
        packed = b"#WDserver:dest:0:1:2:3:4:5:6:7:8:9:10:11:12:13:14:15:16:17:18:19:20:21:22:23"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(WindPacket.unpack(packed + b":1:2:3"), packet)

    def test_CloudPacket(self) -> None:
        packet = CloudPacket(
            b"dest",
            (CloudLayer(0, 1, 2, 3, 4), CloudLayer(5, 6, 7, 8, 9)),
            CloudLayer(10, 11, 12, 13, 14),
            15,
        )
        packed = b"#CDserver:dest:0:1:2:3:4:5:6:7:8:9:10:11:12:13:14:15.00"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(CloudPacket.unpack(packed + b":1:2:3"), packet)

    def test_ReplyAcarsPacket(self) -> None:
        packet = ReplyAcarsPacket(b"dest", b"type", b"data")
        packed = b"$ARserver:dest:type:data"
        self.assertEqual(packed, packet.pack())
        self.assertEqual(ReplyAcarsPacket.unpack(packed + b":1:2:3"), packet)

    def test_try_parse(self) -> None:
        self.assertIsNone(try_parse(b""))
        self.assertIsNone(try_parse(b"#AP:"))
        self.assertEqual(
            try_parse(b"$PIsource:dest:data"),
            MulticastPacket(FSDClientCommand.PING, b"source", b"dest", b"data"),
        )
        self.assertEqual(
            try_parse(b"$PIsource:sErVeR:data"), ServerPingPacket(b"source", b"data")
        )
        self.assertEqual(
            try_parse(b"$PIsource:dest:data"),
            MulticastPacket(FSDClientCommand.PING, b"source", b"dest", b"data"),
        )
        self.assertIsNone(try_parse(b"$CQsource:SERVER"))
        self.assertEqual(
            try_parse(b"$!!source:who:reason"), KillPacket(b"source", b"who", b"reason")
        )
        self.assertEqual(
            try_parse(b"#DPsource"), RemoveClientPacket(False, b"source", None)
        )
