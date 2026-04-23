"""Tools to perform runtime TypedDict type check.

It can be used to perform config check.
Only TypedDict, Literal, (Not)Required, Union, List and Dict are supported.

Attributes:
    DictStructure: Type of a object describes structure of a dict, can be TypedDict
        or dict.
    TypeHint: Type of a type hint.

Examples:
    >>> list(check_simple_type(1, Union[int, str]))
    []
    >>> list(check_simple_type(b"imbytes", Union[int, str]))
    [VerifyTypeError('object', typing.Union[int, str], b'imbytes')]
    >>> list(check_dict({ "a": 1 }, TypedDict("A", { "a": int })))
    []
    >>> list(check_dict({ "a": "imstr" }, TypedDict("A", { "a": int })))
    [VerifyTypeError("dict['a']", <class 'int'>, 'imstr')]
"""

from collections.abc import Hashable, Iterable, Mapping
from types import UnionType
from typing import Any as TypeHint
from typing import (
    Literal,
    Union,
    get_args,
    get_origin,
)
from typing import get_type_hints as legacy_get_type_hints

from typing_extensions import (
    NoExtraItems,
    NotRequired,
    Required,
    get_type_hints,
    is_typeddict,
)

from .utils import is_empty_iterable

__all__ = [
    "DictStructure",
    "TypeHint",
    "VerifyKeyError",
    "VerifyTypeError",
    "assert_dict",
    "assert_simple_type",
    "check_dict",
    "check_simple_type",
    "explain_type",
    "lookup_required",
]


def explain_type(typ: TypeHint) -> str:
    """Explain a type.

    Args:
        typ: The type to be explained.

    Returns:
        Description of the type.

    Raises:
        TypeError: When an unsupported/invalid type passed.
    """
    if isinstance(typ, dict) or is_typeddict(typ):
        return "dict"
    if type_origin := get_origin(typ):  # elif (t_o is not None)
        if type_origin is Union or type_origin is UnionType:
            return " or ".join(explain_type(sub_type) for sub_type in get_args(typ))
        if type_origin is Literal:
            return " or ".join(repr(sub_value) for sub_value in get_args(typ))
        if type_origin in (list, dict):
            return str(typ).removeprefix(typ.__module__ + ".")
        raise TypeError(f"Unsupported type: {type_origin!r}")
    if isinstance(typ, type):
        return typ.__name__
    raise TypeError(f"Invalid type: {typ!r}")


class VerifyTypeError(TypeError):
    """A exception describes a value does not match specified type.

    Attributes:
        name: The name of this value.
        excepted: The expected type.
        actually: The actually value.
    """

    name: str
    excepted: TypeHint
    actually: object

    def __init__(self, name: str, excepted: TypeHint, actually: object) -> None:
        """Create a VerifyTypeError instance.

        Args:
            name: The name of the value.
            excepted: The expected type.
            actually: The actually value.
        """
        self.name = name
        self.excepted = excepted
        self.actually = actually
        super().__init__(name, excepted, actually)

    def __str__(self) -> str:
        """Format a VerifyTypeError to string.

        Returns:
            The formatted string, includes name, expected type and actually value
        """
        return (
            f"'{self.name}' must be {explain_type(self.excepted)}"
            f", not {type(self.actually).__name__}"
        )

    def __eq__(self, other: object) -> bool:
        """Check if another object equals to this ConfigTypeError.

        Returns:
            Equals or not.
        """
        if self is other:
            return True
        if isinstance(other, VerifyTypeError):
            return (
                self.name == other.name
                and self.excepted == other.excepted
                and self.actually == other.actually
            )
        return NotImplemented


class VerifyKeyError(KeyError):
    """A exception describes a missing or extra key in a dict.

    Attributes:
        dict_name: The dict name.
        key: The key name.
        type: Type of error, a missing or extra key found.
    """

    dict_name: str
    key: Hashable
    type: Literal["missing", "extra"]

    def __init__(
        self, dict_name: str, key: Hashable, type_: Literal["missing", "extra"]
    ) -> None:
        """Create a VerifyKeyError instance.

        Args:
            dict_name: The dict name.
            key: The key name.
            type_: Type of error, a missing or extra key found.
        """
        self.dict_name = dict_name
        self.key = key
        self.type = type_
        super().__init__(dict_name, key, type_)

    def __str__(self) -> str:
        """Format a VerifyKeyError to string.

        Returns:
            The formatted string, includes name, error type
        """
        if self.type == "missing":
            return f"missing expected key {self.dict_name}[{self.key!r}]"
        return f"unexpected key {self.dict_name}[{self.key!r}]"

    def __eq__(self, other: object) -> bool:
        """Return self==other."""
        if self is other:
            return True
        if isinstance(other, VerifyKeyError):
            return self.dict_name == other.dict_name and self.type == other.type
        return NotImplemented


def check_simple_type(
    obj: object,
    typ: TypeHint,
    name: str = "object",
) -> Iterable[VerifyTypeError]:
    """Simple runtime type checker, supports Union, Literal, List, Dict.

    Args:
        obj: The object to be verified.
        typ: The expected type. Union, Literal, List, Dict or runtime checkable type
        name: Name of the object.

    Yields:
        When a type error was detected.

    Raises:
        TypeError: When an unsupported type is specified.
    """
    if type_origin := get_origin(typ):  # elif (t_o is not None)
        if type_origin is Union or type_origin is UnionType:
            for sub_type in get_args(typ):
                if is_empty_iterable(check_simple_type(obj, sub_type, name=name)):
                    return
            yield VerifyTypeError(name, typ, obj)
        elif type_origin is Literal:
            if obj not in get_args(typ):
                yield VerifyTypeError(name, typ, obj)
        elif type_origin is list:
            if not isinstance(obj, list):
                yield VerifyTypeError(name, typ, obj)
                return
            for i, val in enumerate(obj):
                yield from check_simple_type(
                    val,
                    get_args(typ)[0],
                    name=f"{name}[{i}]",
                )
        elif type_origin is dict:
            if not isinstance(obj, dict):
                yield VerifyTypeError(name, typ, obj)
                return
            key_type, value_type = get_args(typ)
            for key, value in obj.items():
                # TODO: Better description of key
                yield from check_simple_type(
                    key,
                    key_type,
                    name=f"{name}[{key!r}]",
                )
                yield from check_simple_type(
                    value,
                    value_type,
                    name=f"{name}[{key!r}]",
                )
        else:
            raise TypeError(f"Unsupported type: {type_origin!r}")
    elif isinstance(typ, type):
        if not isinstance(obj, typ):
            yield VerifyTypeError(name, typ, obj)
    else:
        raise TypeError(f"Invalid type: {typ!r}")


def assert_simple_type(
    obj: object,
    typ: TypeHint,
    name: str = "object",
) -> None:
    """Wrapper of check_simple_type, but raise first error.

    Simple runtime type checker, supports Union, Literal, List, Dict.

    Args:
        obj: The object to be verified.
        typ: The expected type. Union, Literal, List, Dict or runtime checkable type
        name: Name of the object.

    Raises:
        VerifyTypeError: When a type error detected.
        TypeError: When an unsupported type is specified.
    """
    try:
        error = next(iter(check_simple_type(obj, typ, name)))
    except StopIteration:
        pass
    else:
        raise error


DictStructure = type | dict


def _lookup_typeddict_required_legacy(typeddict: type) -> Iterable[str]:
    """Lookup required keys in typing.TypedDict for py3.10.

    When typing_extensions.(Not)Required is used with typing.TypedDict on py3.10,
    __required_keys__ is not relieable.
    """

    # typing.get_type_hints in py3.10 won't strip typing_extensions.(Not)Required
    if typeddict.__total__:  # type: ignore[attr-defined]
        for key, type_ in legacy_get_type_hints(typeddict).items():
            if get_origin(type_) is not NotRequired:
                yield key
        return
    for key, type_ in legacy_get_type_hints(typeddict).items():
        if get_origin(type_) is Required:
            yield key


def lookup_required(structure: DictStructure) -> Iterable[str]:
    """Yields all required key in a TypedDict, in sorted order.

    Args:
        structure: The type structure, TypedDict or dict.

    Yields:
        Keys that are required, str normally.
    """
    if is_typeddict(structure):
        if NotRequired.__module__ == "typing":  # Python 3.11+, not need to Workaround
            yield from sorted(structure.__required_keys__)  # type: ignore[union-attr]
            return
        yield from sorted(
            _lookup_typeddict_required_legacy(structure)  # type: ignore[arg-type]
        )
        return
    else:
        for may_required_keys, type_ in sorted(structure.items()):  # type: ignore[union-attr]
            if get_origin(type_) is not NotRequired:
                yield may_required_keys


def check_dict(
    dict_obj: dict,
    structure: DictStructure,
    *,
    name: str = "dict",
) -> Iterable[VerifyTypeError | VerifyKeyError]:
    """Check type of a dict accord TypedDict.

    Args:
        dict_obj: The dict to be checked.
        structure: Expected type.
        name: Name of the dict.

    Yields:
        Detected type error, in VerifyTypeError / VerifyKeyError

    Raises:
        TypeError: When an unsupported/invalid type passed.

    Examples:
        >>> class AType(TypedDict):
        ...     a: int
        ...
        >>> list(check_dict({ "a": 114514 }, AType))
        []
        >>> list(check_dict({ "a": "" }, AType, name="mything"))
        [VerifyTypeError("mything['a']", <class 'int'>, '')]
        >>> list(check_dict({}, AType))
        [VerifyKeyError('dict', 'a', 'missing')]
        >>> list(check_dict(
        ...     { "a": 114514, "b": 1919810 },
        ...     TypedDict("DictA", { "a": int }),
        ...     AType,
        ... ))
        [VerifyKeyError('dict', 'b', 'extra')]
        >>> list(check_dict(
        ...     { "a": 114514, "b": "1919810" },
        ...     TypedDict("DictA", { "a": int }, extra_items=str),
        ... ))
        []
    """

    def deal_dict_not_required(
        dic: Mapping,
    ) -> Iterable[tuple[Hashable, TypeHint | DictStructure]]:
        for key, typ in dic.items():
            if get_origin(typ) in (Required, NotRequired):
                yield key, get_args(typ)[0]
            else:
                yield key, typ

    # All keys presents in dict_obj but not in structure
    left_keys = list(dict_obj.keys())
    required_keys = tuple(lookup_required(structure))
    structure_is_typeddict = is_typeddict(structure)
    for key, type_ in (
        get_type_hints(structure).items()
        if structure_is_typeddict
        else deal_dict_not_required(structure)  # type: ignore[arg-type]
    ):
        try:
            value = dict_obj[key]
        except KeyError:
            if key in required_keys:
                yield VerifyKeyError(name, key, "missing")
            continue
        left_keys.remove(key)
        if is_typeddict(type_) or isinstance(type_, dict):
            if not isinstance(value, dict):
                yield VerifyTypeError(f"{name}[{key!r}]", type_, value)
            else:
                yield from check_dict(
                    value,
                    type_,
                    name=f"{name}[{key!r}]",
                )
        else:
            yield from check_simple_type(value, type_, name=f"{name}[{key!r}]")
    if (
        structure_is_typeddict
        and (extra_items_type := getattr(structure, "__extra_items__", NoExtraItems))
        is not NoExtraItems
    ):
        for key in left_keys:
            yield from check_simple_type(
                dict_obj[key], extra_items_type, name=f"{name}[{key!r}]"
            )
    else:
        yield from (VerifyKeyError(name, key, "extra") for key in left_keys)


def assert_dict(
    dict_obj: dict,
    structure: DictStructure,
    *,
    name: str = "dict",
) -> None:
    """Wrapper of check_dict, which raises once an error is generated.

    Check type of a dict accord TypedDict.

    Args:
        dict_obj: The dict to be checked.
        structure: Expected type.
        name: Name of the dict.

    Raises:
        VerifyTypeError: When found type error.
        VerifyKeyError: When found a type error about key.
        TypeError: When an unsupported/invalid type passed.
    """
    try:
        error = next(
            iter(
                check_dict(
                    dict_obj,
                    structure,
                    name=name,
                )
            )
        )
    except StopIteration:
        pass
    else:
        raise error
