"""PyFSD plugin architecture.

Attributes:
    API_LEVEL (tuple[int, int]): Current PyFSD plugin api level, (major, minor).
        If changes will break something, major is increased, otherwise minor.
    EventResult: event handle result for handleable events.
"""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Literal,
    ParamSpec,
    Union,
    overload,
)

from typing_extensions import TypedDict

if TYPE_CHECKING:
    from pyfsd.client.object import Client
    from pyfsd.client.session import ClientSession
    from pyfsd.define.protocol.packet import ServerBoundPacket

__all__ = [
    "API_LEVEL",
    "EventListenersDict",
    "EventResult",
    "Plugin",
    "PluginHandledEventResult",
    "PreventEvent",
    "PyFSDHandledEventResult",
    "SimplePlugin",
    "StubPlugin",
]


P = ParamSpec("P")
AsyncCallable = Callable[P, Awaitable]
_IterableEventHandlers = Iterable[AsyncCallable[P]]
_EventHandlerDecorator = Callable[[AsyncCallable[P]], AsyncCallable[P]]

API_LEVEL = (5, 0)
EventResult = Union["PluginHandledEventResult", "PyFSDHandledEventResult"]


class PreventEvent(BaseException):
    """Prevent a PyFSD plugin event.

    Attributes:
        result: The event result reported by plugin.
    """

    result: dict

    def __init__(self, result: dict | None = None) -> None:
        """Create a PreventEvent instance."""
        if result is None:
            result = {}
        self.result = result


# TODO: some of them wasn't already applied
class EventHandlersDict(  # type: ignore[call-arg]
    TypedDict,
    extra_items=_IterableEventHandlers[...],
    total=False,
):
    """Event handlers."""

    packet_received: _IterableEventHandlers[["Client", "ServerBoundPacket"]]


class EventAuditersDict(  # type: ignore[call-arg]
    TypedDict,
    extra_items=_IterableEventHandlers[...],
    total=False,
):
    client_disconnected: _IterableEventHandlers[["ClientSession", "Client"]]
    new_connection_established: _IterableEventHandlers[["ClientSession"]]
    packet_received: _IterableEventHandlers[
        ["Client", "ServerBoundPacket", "EventResult"]
    ]
    new_client_created: _IterableEventHandlers[["Client"]]
    before_start: _IterableEventHandlers[[]]
    before_stop: _IterableEventHandlers[[]]


class EventListenersDict(TypedDict):
    """Dict that stores event listeners (handlers & auditers)."""

    handlers: EventHandlersDict
    auditers: EventAuditersDict


class Plugin:
    """Base class of a PyFSD plugin.

    Attributes:
        name: Name of this plugin.
        api: API level of this plugin. See `pyfsd.plugin.API_LEVEL`
        version: int and human readable version of this plugin.
        expected_config: Configuration structure description, in dict or TypedDict,
            which is structure parameter of pyfsd.define.check_dict function.
            use None to disable config check.
    """

    name: str
    api: tuple[int, int]
    version: tuple[int, str]
    expected_config: type[TypedDict] | dict | None  # type: ignore[valid-type]

    def __hash__(self) -> int:
        """Return hash of this plugin."""
        # self.name is ensured to be unique by PluginManager
        return hash(self.name)

    def __eq__(self, value: object, /) -> bool:
        """Check if this plugin equals to another one."""
        if value is self:
            return True
        if isinstance(value, Plugin):
            return (
                self.name == value.name
                and self.api == value.api
                and self.version == value.version
            )
        return NotImplemented

    def __repr__(self) -> str:
        """Return the canonical string representation of this plugin."""
        return f"<PyFSDPlugin {self.name} v{self.version[1]} ({self.version[0]})>"

    async def setup(self) -> EventListenersDict | None:
        """Setup this plugin.

        Returns:
            A dict that stores event listeners. See `pyfsd.plugin.EventListenersDict`
                None if this plugin does not register event listeners.
        """


@dataclass(frozen=True, eq=False, repr=False)
class StubPlugin(Plugin):
    """Stub plugin that does nothing."""

    # TODO: Currently we have to copy these attributes until python 3.10
    # see github issue microsoft/vscode-python#20378
    name: str
    api: tuple[int, int]
    version: tuple[int, str]
    expected_config: type[TypedDict] | dict | None  # type: ignore[valid-type]


@dataclass(frozen=True, eq=False, repr=False)
class SimplePlugin(Plugin):
    """Create a simple plugin by decorators.

    Attributes:
        listeners: Event listeners.
    """

    # TODO: see `pyfsd.plugin.StubPlugin`
    name: str
    api: tuple[int, int]
    version: tuple[int, str]
    expected_config: type[TypedDict] | dict | None  # type: ignore[valid-type]
    listeners: EventListenersDict = field(  # type: ignore[assignment]
        default_factory=lambda: {"auditers": {}, "handlers": {}}
    )
    _pre_setup: AsyncCallable[...] | None = field(init=False, default=None)

    async def setup(self) -> EventListenersDict:
        """Return listeners registered by self.handle() and self.audit() before."""
        if self._pre_setup:
            await self._pre_setup()
        return self.listeners

    @overload
    def handle(
        self, event: Literal["packet_received"]
    ) -> _EventHandlerDecorator[["ClientSession", "ServerBoundPacket"]]: ...
    @overload
    def handle(self, event: str) -> _EventHandlerDecorator[...]: ...

    def handle(self, event: str) -> _EventHandlerDecorator[...]:
        """Add a event handler for specified event."""
        if event not in self.listeners["handlers"]:
            # TODO: mypy hasn't impled extra_items so ignore for now
            self.listeners["handlers"][event] = []  # type: ignore[literal-required]

        def decorator(handler: AsyncCallable[P]) -> AsyncCallable[P]:
            self.listeners["handlers"][event].append(handler)  # type: ignore[literal-required]
            return handler

        return decorator

    @overload
    def audit(
        self, event: Literal["client_disconnected"]
    ) -> _EventHandlerDecorator[["ClientSession", "Client"]]: ...
    @overload
    def audit(
        self, event: Literal["new_connection_established"]
    ) -> _EventHandlerDecorator[["ClientSession"]]: ...
    @overload
    def audit(
        self, event: Literal["packet_received"]
    ) -> _EventHandlerDecorator[
        ["ClientSession", "ServerBoundPacket", "EventResult"]
    ]: ...
    @overload
    def audit(
        self, event: Literal["new_client_created"]
    ) -> _EventHandlerDecorator[["Client"]]: ...
    @overload
    def audit(self, event: Literal["before_start"]) -> _EventHandlerDecorator[[]]: ...
    @overload
    def audit(self, event: Literal["before_stop"]) -> _EventHandlerDecorator[[]]: ...
    @overload
    def audit(self, event: str) -> _EventHandlerDecorator[...]: ...

    def audit(self, event: str) -> _EventHandlerDecorator[...]:
        """Add a event auditer for specified event."""
        if event not in self.listeners["auditers"]:
            self.listeners["auditers"][event] = []  # type: ignore[literal-required]

        def decorator(auditer: AsyncCallable[P]) -> AsyncCallable[P]:
            self.listeners["auditers"][event].append(auditer)  # type: ignore[literal-required]
            return auditer

        return decorator

    def setuper(self, setuper: AsyncCallable[P]) -> AsyncCallable[P]:
        """Set setuper."""
        object.__setattr__(self, "_pre_setup", setuper)
        return setuper


class PluginHandledEventResult(TypedDict):
    """A result handled by plugin.

    This means a plugin raised `pyfsd.plugin.PreventEvent`.

    Attributes:
        handled_by_plugin: Event handled by plugin or not.
        plugin_name: Name of the plugin.
    """

    handled_by_plugin: Literal[True]
    plugin: Plugin


class PyFSDHandledEventResult(TypedDict):
    """A result handled by PyFSD.

    Attributes:
        handled_by_plugin: Event handled by plugin or not.
        success: The event successfully handled or not.
    """

    handled_by_plugin: Literal[False]
    success: bool
