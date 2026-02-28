"""Utilities to deal with FSD packet.

Attributes:
    CLIENT_USED_COMMAND (list[FSDClientCommand]): All possibly command can be issued by
        user in protocol 9.
    SPLIT_SIGN (bytes): FSD client packet's split sign.
"""

from collections.abc import Iterable
from enum import Enum
from typing import overload

__all__ = [
    "CLIENT_USED_COMMAND",
    "SPLIT_SIGN",
    "FSDClientCommand",
    "break_packet",
    "join_lines",
    "make_packet",
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


def make_packet(*parts: bytes) -> bytes:
    """Join parts together and add split sign between every two parts."""
    result = b""
    for part in parts:
        result += part + SPLIT_SIGN
    return result[:-1]


@overload
def break_packet(
    packet: bytes,
    possibly_commands: Iterable[FSDClientCommand],
) -> tuple[FSDClientCommand | None, tuple[bytes, ...]]: ...


@overload
def break_packet(
    packet: bytes,
    possibly_commands: Iterable[bytes],
) -> tuple[bytes | None, tuple[bytes, ...]]: ...


def break_packet(
    packet: bytes,
    possibly_commands: Iterable[bytes | FSDClientCommand],
) -> tuple[bytes | FSDClientCommand | None, tuple[bytes, ...]]:
    """Break a packet into command and parts.

        #APzzzzzzzzzzzz1:zzzzzzz3:zzzzzzz4
        [^][^^^^^^^^^^^] [^^^^^^] [^^^^^^]
        command parts[0] parts[1] parts[2]

    Args:
        packet: The original packet.
        possibly_commands: All possibly commands. This function will check if packet \
            starts with one of possibly commands then split it out.

    Returns:
        tuple[command or None, tuple[every_part, ...]]
    """
    command: bytes | FSDClientCommand | None = None
    splited_packet = packet.split(SPLIT_SIGN)
    for possibly_command in possibly_commands:
        if not packet.startswith(possibly_command):
            continue
        command = possibly_command
        splited_packet[0] = splited_packet[0][len(command) :]
    return (command, tuple(splited_packet))


def join_lines(*lines: bytes, newline: bool = True) -> bytes:
    r"""Join lines together.

    Args:
        lines: The lines.
        newline: Append '\r\n' to every line or not.

    Returns:
        The result.
    """
    result = b""
    split_sign = b"\r\n"
    for line in lines:
        result += line + split_sign if newline else line
    return result


CLIENT_USED_COMMAND = [
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
