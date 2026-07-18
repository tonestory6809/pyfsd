"""FSD protocol 9 constants.

Attributes:
    SERVER_BOUND_COMMAND (list[FSDClientCommand]): All possibly command can be issued by
        user in protocol 9.
    SPLIT_SIGN (bytes): FSD client packet's split sign.
"""

from enum import Enum

__all__ = [
    "SERVER_BOUND_COMMAND",
    "SPLIT_SIGN",
    "FSDClientCommand",
]

SPLIT_SIGN = b":"


class FSDClientCommand(bytes, Enum):
    """FSD client command."""

    ADD_ATC = b"#AA"
    REMOVE_ATC = b"#DA"
    ADD_PILOT = b"#AP"
    REMOVE_PILOT = b"#DP"
    REQUEST_HANDOFF = b"$HO"
    MESSAGE = b"#TM"
    REQUEST_WEATHER = b"#RW"
    PILOT_POSITION = b"@"
    ATC_POSITION = b"%"
    PING = b"$PI"
    PONG = b"$PO"
    ACCEPT_HANDOFF = b"$HA"
    PLAN = b"$FP"
    SQUAWK_BOX = b"#SB"
    PRO_CONTROLLER = b"#PC"
    WEATHER = b"#WX"
    CLOUD_DATA = b"#CD"
    WIND_DATA = b"#WD"
    TEMP_DATA = b"#TD"
    REQUEST_COMM = b"$C?"
    REPLY_COMM = b"$CI"
    REQUEST_ACARS = b"$AX"
    REPLY_ACARS = b"$AR"
    ERROR = b"$ER"
    CLIENT_QUERY = b"$CQ"
    CLIENT_RESPONSE = b"$CR"
    KILL = b"$!!"
    WIND_DELTA = b"#DL"


SERVER_BOUND_COMMAND = [
    FSDClientCommand.ADD_ATC,
    FSDClientCommand.REMOVE_ATC,
    FSDClientCommand.ADD_PILOT,
    FSDClientCommand.REMOVE_PILOT,
    FSDClientCommand.REQUEST_HANDOFF,
    FSDClientCommand.PILOT_POSITION,
    FSDClientCommand.ATC_POSITION,
    FSDClientCommand.PING,
    FSDClientCommand.PONG,
    FSDClientCommand.MESSAGE,
    FSDClientCommand.ACCEPT_HANDOFF,
    FSDClientCommand.PLAN,
    FSDClientCommand.SQUAWK_BOX,
    FSDClientCommand.PRO_CONTROLLER,
    FSDClientCommand.WEATHER,
    FSDClientCommand.REQUEST_COMM,
    FSDClientCommand.REPLY_COMM,
    FSDClientCommand.REQUEST_ACARS,
    FSDClientCommand.CLIENT_QUERY,
    FSDClientCommand.CLIENT_RESPONSE,
    FSDClientCommand.KILL,
]
