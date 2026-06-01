"""Run PyFSD.

Attributes:
    DEFAULT_CONFIG (str): Default config of PyFSD.
"""

from argparse import ArgumentParser
from asyncio import (
    AbstractEventLoop,
    CancelledError,
    Task,
    all_tasks,
    create_task,
    current_task,
    gather,
    get_running_loop,
    set_event_loop,
    shield,
    wait,
)
from asyncio import (
    new_event_loop as aio_new_event_loop,
)
from signal import SIGINT
from typing import cast

from dependency_injector.wiring import register_loader_containers
from structlog import get_logger
from typing_extensions import NotRequired, TypedDict

from ._version import version
from .db_tables import metadata
from .define.check_dict import assert_dict
from .define.utils import logged_task, mustdone_task_keeper, task_keeper
from .dependencies import Container
from .factory.client import PyFSDClientConfig
from .metar.manager import PyFSDMetarConfig, suppress_metar_parser_warning
from .setup_logger import PyFSDLoggerConfig, setup_logger

try:
    from tomllib import loads  # type: ignore[import-not-found,unused-ignore]
except ImportError:
    # Python 3.11+
    from tomli import loads  # type: ignore[no-redef,import-not-found,unused-ignore]


class PyFSDDatabaseConfig(TypedDict, extra_items=object):  # type: ignore[call-arg]
    """PyFSD database config.

    Attributes:
        url: The database url, see
            [SQLALchemy docs](https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls).
    """

    url: str


class PyFSDConfig(TypedDict):
    """PyFSD config."""

    database: PyFSDDatabaseConfig
    client: PyFSDClientConfig
    metar: PyFSDMetarConfig
    logger: PyFSDLoggerConfig


class RootPyFSDConfig(TypedDict):
    """PyFSD root config."""

    pyfsd: PyFSDConfig
    plugin: NotRequired[dict]


logger = get_logger(__name__)

DEFAULT_CONFIG = """[pyfsd.database]
url = "sqlite:///pyfsd.db"

[pyfsd.client]
port = 6809
motd = \"\"\"Modify motd in pyfsd.toml.\"\"\"
motd_encoding = "ascii"
blacklist = []

[pyfsd.metar]
mode = "cron"
cron_time = 3600
fetchers = ["noaa"]

[pyfsd.logger.root_logger]
handlers = ["default"]
level = "DEBUG"

[pyfsd.logger.handlers.default]
level = "INFO"
class = "logging.StreamHandler"
formatter = "colored"
"""


async def launch(config: RootPyFSDConfig, *, wait_all_tasks_done: bool = True) -> None:
    """Launch PyFSD."""
    # Specify a driver in DB url
    db_url: str = config["pyfsd"]["database"]["url"]
    scheme, url = db_url.split("://", 1)
    if "+" not in scheme:  # if user does not specify driver
        if scheme == "postgresql":
            db_url = "postgresql+asyncpg://" + url
        elif scheme in ("mysql", "mariadb"):
            db_url = "mysql+asyncmy://" + url
        elif scheme == "sqlite":
            db_url = "sqlite+aiosqlite://" + url
        elif scheme == "oracle":
            db_url = "oracle+oracledb_async://" + url
        elif scheme == "mssql":
            db_url = "mssql+aioodbc://" + url
        config["pyfsd"]["database"]["url"] = db_url
    # =============== Initialize dependencies
    container = Container()
    container.config.from_dict(config)
    register_loader_containers(container)  # Register
    # Then load plugins to wire them
    pm = container.plugin_manager()
    await pm.pick_plugins(config.get("plugin", {}))
    container.metar_manager().check_fetchers()
    # Initialize database
    try:
        async with container.db_engine().begin() as conn:
            await conn.run_sync(metadata.create_all)
    except Exception as exc:
        raise RuntimeError(
            "Failed to initialize database, is it configured correctly?"
        ) from exc
    # =============== Startup
    loop = get_running_loop()
    client_server = await loop.create_server(
        container.client_factory(),
        port=config["pyfsd"]["client"]["port"],
    )
    await container.plugin_manager().trigger_event_auditers("before_start", (), {})
    await logger.ainfo(f"PyFSD {version}")

    plugins_count = pm.plugins_count()
    await logger.ainfo(
        f"{plugins_count} plugins: {pm!s}" if plugins_count else "0 plugins"
    )
    tasks_pyfsd = [
        container.client_factory().get_heartbeat_task(),
        logged_task(create_task(client_server.serve_forever())),
    ]
    if container.metar_manager().cron_time:
        tasks_pyfsd.append(
            container.metar_manager().get_cron_task(),
        )
    try:
        await shield(gather(*tasks_pyfsd, return_exceptions=True))
    except CancelledError:
        # =========== Stop
        await logger.ainfo("Stopping")
        client_server.close()
        await container.plugin_manager().trigger_event_auditers("before_stop", (), {})
        container.client_factory().remove_all_clients()
        await client_server.wait_closed()
        for task in tasks_pyfsd:
            task.cancel()
        for task in task_keeper.tasks:
            task.cancel()
        await gather(*tasks_pyfsd, *task_keeper.tasks, return_exceptions=True)
        if wait_all_tasks_done:
            tasks = all_tasks()
            tasks.discard(cast("Task", current_task()))
        else:
            tasks = mustdone_task_keeper.tasks
        if tasks:
            total_wait_seconds = 0
            while True:
                total_wait_seconds += 5
                _, pending = await wait(tasks, timeout=5)
                if not pending:
                    break
                await logger.adebug(
                    f"Waited {total_wait_seconds} second, "
                    "but these tasks are still running",
                    stack="\n".join(f"  {task!s}" for task in pending),
                )
        await container.db_engine().dispose()
        raise


def main() -> None:
    """Main function of PyFSD."""
    # =============== Config
    parser = ArgumentParser()
    parser.add_argument(
        "-c",
        "--config-path",
        help="Path to the config file.",
        default="pyfsd.toml",
        type=str,
    )
    args = parser.parse_args()
    try:
        with open(args.config_path) as config_file:
            config = loads(config_file.read())
    except FileNotFoundError:
        with open(args.config_path, "w") as config_file:
            config_file.write(DEFAULT_CONFIG)
        config = loads(DEFAULT_CONFIG)

    assert_dict(
        config,
        RootPyFSDConfig,
        name="config",
    )

    # =============== Logger
    suppress_metar_parser_warning()
    setup_logger(config["pyfsd"]["logger"], finalize=False)

    # =============== Startup
    loop: AbstractEventLoop
    try:
        from uvloop import new_event_loop as uv_new_event_loop

        loop = uv_new_event_loop()
    except ImportError:
        loop = aio_new_event_loop()

    set_event_loop(loop)

    sigint_count = 0

    def sigint_handler() -> None:
        nonlocal sigint_count
        if sigint_count:
            raise KeyboardInterrupt()
        main_task.cancel()
        loop.call_soon_threadsafe(lambda: None)
        sigint_count += 1

    main_task = loop.create_task(launch(cast("RootPyFSDConfig", config)))

    loop.add_signal_handler(SIGINT, sigint_handler)
    try:
        loop.run_until_complete(main_task)
    except CancelledError:
        pass
    except KeyboardInterrupt:

        async def shutdown() -> None:
            tasks = all_tasks()
            tasks.discard(cast("Task", current_task()))
            for task in tasks:
                task.cancel()
            await gather(*tasks, return_exceptions=True)

        loop.run_until_complete(shutdown())

    except BaseException:
        logger.exception("Error happened when launching PyFSD")

    # =============== Finalize
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.run_until_complete(loop.shutdown_default_executor())
    set_event_loop(None)
    loop.close()
    # Ensure we have working loggers when cpython is shutting down
    setup_logger(config["pyfsd"]["logger"], finalize=True)
