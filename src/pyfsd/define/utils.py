"""Collection of tools that are used frequently.

Attributes:
    task_keeper (TaskKeeper): Helper to keep your asyncio.Task's strong reference and
        cancel it when PyFSD is shutting down.
    mustdone_task_keeper (TaskKeeper): Similar to task_keeper, but PyFSD will await
        them before stop.
"""

import re
from asyncio import get_running_loop
from collections.abc import Awaitable, Callable, Hashable, Iterable
from functools import wraps
from itertools import chain as iterables
from typing import (
    TYPE_CHECKING,
    TypeVar,
    cast,
)

from haversine import Unit, haversine
from typing_extensions import ParamSpec

if TYPE_CHECKING:
    from asyncio import Task

    from pyfsd.object.client import Position

__all__ = [
    "MRand",
    "assert_no_duplicate",
    "asyncify",
    "atoi",
    "calc_distance",
    "is_callsign_valid",
    "is_empty_iterable",
    "iter_callable",
    "iterables",
    "join_lines",
    "mustdone_task_keeper",
    "str_to_float",
    "str_to_int",
    "task_keeper",
]
T = TypeVar("T")
atoi_pattern = re.compile(rb"(?a)\s*([-+]?\d+)")


def str_to_int(string: str | bytes, default_value: int = 0) -> int:
    """Convert a str or bytes into int.

    Args:
        string: The string to be converted.
        default_value: Default value when convert failed.

    Returns:
        The int.
    """
    try:
        return int(string)
    except ValueError:
        return default_value


def str_to_float(string: str | bytes, default_value: float = 0.0) -> float:
    """Convert a str or bytes into float.

    Args:
        string: The string to be converted.
        default_value: Default value when convert failed.

    Returns:
        The float number.
    """
    try:
        return float(string)
    except ValueError:
        return default_value


def atoi(s: bytes) -> int:
    """atoi implementation that SIMILAR to what in ANSI C."""
    match = atoi_pattern.match(s)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return -1


def calc_distance(
    from_position: "Position",
    to_position: "Position",
    unit: Unit = Unit.NAUTICAL_MILES,
) -> float:
    """Calculate the distance from one point to another point.

    A wrapper of haversine since it's not typed well

    Args:
        from_position: The first point.
        to_position: The second point.
        unit: Unit of the distance, nm by default.

    Returns:
        The distance.
    """
    return cast("float", haversine(from_position, to_position, unit=unit))


CALLSIGN_MIN_LEN = 2
CALLSIGN_MAX_LEN = 12


def is_callsign_valid(callsign: str | bytes) -> bool:
    """Check if a callsign is valid or not."""
    if not CALLSIGN_MIN_LEN < len(callsign) < CALLSIGN_MAX_LEN:
        return False
    if isinstance(callsign, str):
        return not (
            ("!" in callsign)
            or ("@" in callsign)
            or ("#" in callsign)
            or ("$" in callsign)
            or ("%" in callsign)
            or ("*" in callsign)
            or (":" in callsign)
            or ("&" in callsign)
            or (" " in callsign)
            or ("\t" in callsign)
        )
    return not (
        (b"!" in callsign)
        or (b"@" in callsign)
        or (b"#" in callsign)
        or (b"$" in callsign)
        or (b"%" in callsign)
        or (b"*" in callsign)
        or (b":" in callsign)
        or (b"&" in callsign)
        or (b" " in callsign)
        or (b"\t" in callsign)
    )


def assert_no_duplicate(
    iterator: Iterable[Hashable],
) -> None:
    """Assert nothing duplicated in a iterable object.

    Args:
        iterator: The iterable object.

    Raises:
        AssertionError: When a duplicated value detected
    """
    list_val = list(iterator)
    nodup_list_val = list(set(list_val))

    if len(list_val) != len(nodup_list_val):
        for nodup_val in nodup_list_val:
            list_val.remove(nodup_val)
        raise AssertionError(f"Duplicated value: {list_val}")


def is_empty_iterable(iter_obj: Iterable) -> bool:
    """Check if a iterable object is empty."""
    try:
        next(iter(iter_obj))
    except StopIteration:
        return True
    else:
        return False


def iter_callable(obj: object, *, ignore_private: bool = True) -> Iterable[Callable]:
    """Yields all callable attribute in a object.

    Args:
        obj: The object.
        ignore_private: Don't yield attributes which name starts with '_'.

    Yields:
        Callable attributes.
    """
    for attr_name in dir(obj):
        if ignore_private and attr_name.startswith("_"):
            continue
        attr = getattr(obj, attr_name)
        if callable(attr):
            yield attr


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


_T_Task = TypeVar("_T_Task", bound="Task")


def logged_task(task: _T_Task) -> _T_Task:
    """Receive a Task, add exception handler to it and return."""

    def callback(task: "Task") -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is None:
            return
        task.get_loop().call_exception_handler(
            {
                "message": "Uncaught exception in Task",
                "exception": exc,
                "future": task,
            }
        )

    task.add_done_callback(callback)
    return task


P = ParamSpec("P")


def asyncify(func: Callable[P, T]) -> Callable[P, Awaitable[T]]:
    """Decorator to patch a sync function to become async by execute it in thread.

    Examples:
        >>> @asyncify
        >>> def blocking_func():
        ...     sleep(100) # Blocking call
        ...
        >>> async def another_func():
        ...     await blocking_func()  # Not blocking anymore
    """

    @wraps(func)
    async def _call(*args: P.args, **kwargs: P.kwargs) -> T:
        loop = get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    return _call


class MRand:
    """Python implementation of FSD MRand.

    Note:
        This class does not simulate int32 overflow.
        See also: pyfsd.define.simulation.Int32MRand

    Attributes:
        mrandseed: Random seed.
    """

    mrandseed: int = 0

    def __call__(self) -> int:
        """Generate a random number."""
        self.mrandseed ^= 0x22591D8C
        part1 = (self.mrandseed << 1) & 0xFFFFFFFF
        part2 = self.mrandseed >> 31
        self.mrandseed ^= part1 | part2
        return self.mrandseed

    def srand(self, seed: int) -> None:
        """Set random seed."""
        self.mrandseed = seed


class TaskKeeper:
    """Helper to keep strong reference of running [asyncio.Task][]s.

    Note:
        You're advised not to create new instance and use
            pyfsd.define.utils.task_keeper instead.
    """

    tasks: set["Task"]

    def __init__(self) -> None:
        """Create a TaskKeeper instance."""
        self.tasks = set()

    def cancel_all(self) -> None:
        """Cancel all tasks."""
        for task in self.tasks:
            task.cancel()

    def add(self, task: "Task") -> None:
        """Add a task that to be kept."""
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


task_keeper = TaskKeeper()
mustdone_task_keeper = TaskKeeper()
