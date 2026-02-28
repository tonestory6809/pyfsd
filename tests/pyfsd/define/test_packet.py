"""This module tests pyfsd.define.packet."""

from unittest import TestCase

from pyfsd.define.packet import (
    CLIENT_USED_COMMAND,
    FSDClientCommand,
    break_packet,
    join_lines,
    make_packet,
)


class TestPacket(TestCase):
    """Test if pyfsd.define.packet works."""

    def test_make_packet(self) -> None:
        """Test if make_packet works."""
        self.assertEqual(make_packet(b"abcd", b"efgh"), b"abcd:efgh")
        self.assertEqual(
            make_packet(FSDClientCommand.ADD_PILOT, b"CSN1012"), b"#AP:CSN1012"
        )
        self.assertEqual(
            make_packet(b"CSN1012", FSDClientCommand.MESSAGE), b"CSN1012:#TM"
        )

    def test_break_packet(self) -> None:
        """Test if break_packet works."""
        self.assertEqual(
            break_packet(b"#APCSN1012:114514:1919810", FSDClientCommand),
            (FSDClientCommand.ADD_PILOT, (b"CSN1012", b"114514", b"1919810")),
        )
        self.assertEqual(
            break_packet(b"$NMCSN1012:114514:1919810", FSDClientCommand),
            (None, (b"$NMCSN1012", b"114514", b"1919810")),
        )

    def test_join_lines(self) -> None:
        """Test if join_lines works."""
        self.assertEqual(join_lines(b"a", b"b"), b"a\r\nb\r\n")
        self.assertEqual(join_lines(b"a", b"b", newline=False), b"ab")

    def test_CLIENT_USED_COMMAND(self) -> None:
        """Test if CLIENT_USED_COMMAND works."""
        for command in CLIENT_USED_COMMAND:
            with self.subTest(command=command):
                self.assertIn(command, FSDClientCommand)
