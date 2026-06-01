# https://www.structlog.org/en/stable/standard-library.html
"""Logger configurer."""

from logging.config import dictConfig

from structlog import (
    configure,
    dev,
    processors,
    reset_defaults,
    stdlib,
)
from structlog.typing import EventDict
from typing_extensions import NotRequired, Required, TypedDict

HandlerConfig = TypedDict(  # type: ignore[misc]
    "HandlerConfig",
    {"class": Required[str], "level": str, "formatter": str, "filters": list[str]},
    total=False,
    extra_items=object,
)


class LoggerConfig(TypedDict, total=False):
    """Type of logger in logging.config.dictConfig."""

    level: str
    propagate: bool
    filters: list[str]
    handlers: list[str]


class TimeFormatConfig(TypedDict, total=False):
    """Config of time formatter.

    Attributes:
        fmt: "iso" for ISO 8601, or "timestamp" for UNIX timestamp, or strftime format string
        utc: Whether timestamp should be in UTC or local time.
    """

    fmt: str
    utc: bool


class PyFSDLoggerConfig(TypedDict):
    """PyFSD logger config. See logging.config.dictConfig."""

    handlers: dict[str, HandlerConfig]
    root_logger: LoggerConfig
    loggers: NotRequired[dict[str, LoggerConfig]]
    time: NotRequired[TimeFormatConfig]


def setup_logger(config: PyFSDLoggerConfig, *, finalize: bool = False) -> None:
    """Setup logger with config.

    Args:
        config: logger config.
        finalize: make loggers fit finalizing phrase of cpython.
    """

    def callsite_to_logger_name(_: object, __: str, event: EventDict) -> EventDict:
        if (funcname := event.pop("func_name", None)) is not None:
            event["logger_name"] = f"{funcname}:{event.pop('lineno')}"
        return event

    time = config.get("time", {})
    fmt: str | None = time.get("fmt", "%Y-%m-%d %H:%M:%S")
    if finalize:
        # For some reason strftime() won't work when cpython is finalizing
        fmt = "iso"
    elif fmt == "timestamp":
        fmt = None
    timestamper = processors.TimeStamper(fmt, utc=time.get("utc", False))
    pre_chain = [
        # Add the log level and a timestamp to the event_dict if the log entry
        # is not from structlog.
        stdlib.add_log_level,
        stdlib.add_logger_name,
        stdlib.ExtraAdder(),
        timestamper,
    ]

    reset_defaults()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": stdlib.ProcessorFormatter,
                    "processors": [
                        processors.dict_tracebacks,
                        stdlib.ProcessorFormatter.remove_processors_meta,
                        processors.JSONRenderer(),
                    ],
                    "foreign_pre_chain": pre_chain,
                },
                "logfmt": {
                    "()": stdlib.ProcessorFormatter,
                    "processors": [
                        processors.dict_tracebacks,
                        stdlib.ProcessorFormatter.remove_processors_meta,
                        processors.LogfmtRenderer(),
                    ],
                    "foreign_pre_chain": pre_chain,
                },
                "plain": {
                    "()": stdlib.ProcessorFormatter,
                    "processors": [
                        callsite_to_logger_name,
                        stdlib.ProcessorFormatter.remove_processors_meta,
                        dev.ConsoleRenderer(
                            colors=False,
                            exception_formatter=dev.better_traceback
                            if not finalize
                            else dev.plain_traceback,
                        ),
                    ],
                    "foreign_pre_chain": pre_chain,
                },
                "colored": {
                    "()": stdlib.ProcessorFormatter,
                    "processors": [
                        callsite_to_logger_name,
                        stdlib.ProcessorFormatter.remove_processors_meta,
                        dev.ConsoleRenderer(
                            colors=True,
                            exception_formatter=dev.better_traceback
                            if not finalize
                            else dev.plain_traceback,
                        ),
                    ],
                    "foreign_pre_chain": pre_chain,
                },
            },
            "loggers": config.get("loggers", {}),
            "handlers": config["handlers"],
            "root": config["root_logger"],
        }
    )
    configure(
        processors=[
            stdlib.filter_by_level,
            processors.CallsiteParameterAdder(
                [
                    processors.CallsiteParameter.FUNC_NAME,
                    processors.CallsiteParameter.LINENO,
                ]
            ),
            stdlib.add_log_level,
            stdlib.add_logger_name,
            stdlib.PositionalArgumentsFormatter(),
            timestamper,
            processors.StackInfoRenderer(),
            stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=stdlib.LoggerFactory(),
        wrapper_class=stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
