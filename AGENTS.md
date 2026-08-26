# PyFSD agent notes

PyFSD is an asyncio TCP server implementing FSD protocol 9.  
Prefer preserving the public protocol and plugin contracts over relying on a
particular internal directory layout: this project may be refactored.

## Orientation

- `src/pyfsd/main.py` owns configuration, startup/shutdown, database setup, and
  the TCP listener.
- `src/pyfsd/client/net/` owns a connection's asyncio protocol, authentication,
  packet dispatch, and the shared `ClientFactory` (online clients, sessions,
  broadcasts, heartbeat).
- `src/pyfsd/define/protocol/` defines FSD packet dataclasses and parsing.
- `src/pyfsd/define/utils.py` provides useful utilities including `task_keeper`
  for keeping reference to short-lived tasks.
- `src/pyfsd/client/object.py` holds the mutable in-memory `Client` state.
- `src/pyfsd/metar/` provides METAR fetching/caching.
- `src/pyfsd/plugin/` is the plugin API and discovery/dispatch mechanism;
  `src/pyfsd/dependencies.py` defines injectable services.

## Plugin contract

Plugins are direct modules discoverable below the extensible `pyfsd.plugins`
namespace (the local development location is normally `pyfsd_plugins/*.py`).  
Each module must export a `pyfsd_plugin` instance of `Plugin` or `SimplePlugin`.  
Use the current `pyfsd.plugin.API_LEVEL` for the plugin's `api` field; it is
currently `(5, 0)`.  A plugin's major level must match exactly and its minor
level cannot exceed the server's.

Use `SimplePlugin` for ordinary plugins:

```python
from pyfsd.plugin import SimplePlugin

pyfsd_plugin = SimplePlugin(
    "example",  # plugin name
    (5, 0),  # expected API version
    (1, "0.1.0"),  # numeric and string version
    {"enabled": bool}  # Optional config
)

@pyfsd_plugin.audit("before_start")
async def startup() -> None: ...
```

`expected_config` validates `[plugin.example]` in `pyfsd.toml`; set it to
`None` when no configuration is required.  
Do not perform initialization at module import time since dependencies has not
yet been injected—use `@pyfsd_plugin.setuper` or lifecycle events instead.

## Events

Handlers run in plugin order before built-in handling.  Raise `PreventEvent()`
only when the plugin has fully handled the event; it stops later handlers and
the built-in handler.  Auditers observe outcomes and run asynchronously, so
they must not be used when the caller needs a result.

- `@pyfsd_plugin.handle("packet_received")`: `(session, ServerBoundPacket)`.
- `@pyfsd_plugin.handle("protocol_9_unparsed_packet")`: `(session, raw_bytes)`
  for protocol extensions not parsed by the core.
- `@pyfsd_plugin.audit("new_connection_established")`: `(session)`.
- `@pyfsd_plugin.audit("new_client_created")`: `(client)` after login.
- `@pyfsd_plugin.audit("client_disconnected")`: `(session, client_or_none)`.
- `@pyfsd_plugin.audit("packet_received")`: `(session, packet, result)`.
- `before_start` and `before_stop`: no arguments; use these for owned service
  startup and cleanup.

Keep handler/auditer functions async.  Plugin exceptions are logged and
isolated; do not rely on an exception to reject a packet.

## Dependency injection

Inject core services with `dependency_injector.wiring` after importing
`Container`.  Available stable providers are `Container.config`,
`Container.db_engine`, `Container.client_factory`, `Container.metar_manager`,
and `Container.plugin_manager`.

```python
from dependency_injector.wiring import Provide, inject
from pyfsd.dependencies import Container

@inject
async def on_start(
    factory = Provide[Container.client_factory],
    config: dict = Provide[Container.config],
) -> None:
    # config["plugin"]["example"] is this plugin's validated configuration
    ...
```

Apply `@inject` to the callable that is invoked after plugin loading; when
combined with other decorators it must be the innermost decorator.  Import-time
calls happen before the plugin module is wired and will receive a `Provide`
placeholder instead of a real service.  Put that work in `setup` or a lifecycle
event.  Database work is async and should use `async with db_engine.begin()`.

## Working conventions

- Keep network handlers non-blocking; create and track background work through
  the project's task helpers when it must outlive an event.
- Treat packet data and callsigns as `bytes` unless an API explicitly exposes
  text.  Preserve FSD wire-format behavior when extending packets.
- See `CONTRIBUTING.md` for important development tools.
- Do not overwrite local plugins, configuration, databases, or unrelated dirty
  worktree changes while implementing a task.

