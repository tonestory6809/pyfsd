"""This module tests pyfsd.define.check_dict."""

# ruff: noqa: UP035
from typing import Dict, Literal, TypedDict, Union
from unittest import TestCase

from typing_extensions import NoExtraItems, NotRequired, Required
from typing_extensions import TypedDict as new_TypedDict

available_typeddict: tuple
if new_TypedDict.__module__ == "typing":
    available_typeddict = (new_TypedDict,)
else:
    available_typeddict = (TypedDict, new_TypedDict)


from pyfsd.define.check_dict import (
    VerifyKeyError,
    VerifyTypeError,
    assert_dict,
    assert_simple_type,
    check_dict,
    check_simple_type,
    explain_type,
    lookup_required,
)


class TestCheckDict(TestCase):
    """Test if pyfsd.define.check_dict works."""

    # ruff: noqa: UP006, UP007
    complex_type = Union[
        int | complex, Literal["1234", 5678], list[str], Dict[int, str]
    ]

    def test_explain_type(self) -> None:
        """Tests if explain_type works."""
        self.assertEqual(
            explain_type(self.complex_type),
            "int or complex or '1234' or 5678 or list[str] or Dict[int, str]",
        )

    def test_explain_error(self) -> None:
        """Tests if verify errors can correctly introduce themselves."""
        self.assertEqual(
            str(VerifyTypeError("abcd", self.complex_type, b"")),
            "'abcd' must be int or complex or '1234' or 5678 or list[str] "
            "or Dict[int, str], not bytes",
        )
        self.assertEqual(
            str(VerifyKeyError("abcd", "efgh", "missing")),
            "missing expected key abcd['efgh']",
        )
        self.assertEqual(
            str(VerifyKeyError("abcd", "efgh", "extra")),
            "unexpected key abcd['efgh']",
        )

    def test_check_simple_type(self) -> None:
        """Tests if check_simple_type works."""

        def generate_simple_case(
            correctv: object, typ: object, wrongv: object
        ) -> tuple[object, object, object, tuple[VerifyTypeError]]:
            return (correctv, typ, wrongv, (VerifyTypeError("obj", typ, wrongv),))

        # case like (correct_value, type, wrong_value, expected_exceptions)
        cases = (
            generate_simple_case(1, Union[int, bytes], "1"),
            generate_simple_case(b"1", int | bytes, "1"),
            generate_simple_case("1234", Literal["1234", 5678], "5678"),
            (
                ["123", "456"],
                list[str],
                [123, 456],
                (
                    VerifyTypeError("obj[0]", str, 123),
                    VerifyTypeError("obj[1]", str, 456),
                ),
            ),
            (
                {1: "1", 2: "2"},
                dict[int, str],
                {"1": 1, "2": 2},
                (
                    VerifyTypeError("obj['1']", int, "1"),
                    VerifyTypeError("obj['1']", str, 1),
                    VerifyTypeError("obj['2']", int, "2"),
                    VerifyTypeError("obj['2']", str, 2),
                ),
            ),
        )
        for correctv, typ, wrongv, expt_exc in cases:
            with self.subTest(typ=typ):
                # Check correct value
                with self.assertRaises(StopIteration):
                    next(iter(check_simple_type(correctv, typ, "obj")))
                assert_simple_type(correctv, typ, "obj")
                # Check wrong value
                self.assertEqual(tuple(check_simple_type(wrongv, typ, "obj")), expt_exc)
                with self.assertRaises(VerifyTypeError) as cm:
                    assert_simple_type(wrongv, typ, "obj")
                self.assertEqual(cm.exception, expt_exc[0])

    def test_lookup_required(self) -> None:
        """Tests if lookup_required works."""
        some_optional_dict = {"a": int, "b": NotRequired[str], "c": Required[bytes]}
        self.assertEqual(tuple(lookup_required(some_optional_dict)), ("a", "c"))
        for typed_dict in available_typeddict:
            with self.subTest(typeddict_source=typed_dict.__module__):

                class SomeOptionalDictA(typed_dict):  # type: ignore[misc, valid-type]
                    a: int
                    b: NotRequired[str]  # type: ignore[valid-type]
                    c: Required[bytes]  # type: ignore[valid-type]

                some_optional_dict_struct = {
                    "a": int,
                    "b": NotRequired[str],
                    "c": Required[bytes],
                }

                self.assertEqual(tuple(lookup_required(SomeOptionalDictA)), ("a", "c"))
                self.assertEqual(
                    tuple(lookup_required(some_optional_dict_struct)), ("a", "c")
                )

                class SomeOptionalDictB(
                    typed_dict,  # type: ignore[misc, valid-type]
                    total=False,  # type: ignore[call-arg]
                ):
                    a: int
                    b: Required[str]  # type: ignore[valid-type]

                self.assertEqual(tuple(lookup_required(SomeOptionalDictB)), ("b",))

    def test_check_dict(self) -> None:
        """Tests if check_dict works."""
        #                               (  expected_errors  )
        normal_cases: tuple[tuple[dict, tuple[Exception, ...]], ...] = (
            (
                {
                    "a": 1,
                    "b": 1234,
                    "c": [1234, 5678],
                    "d": {12: "34", 56: "78"},
                },
                (),
            ),
            (
                {
                    "a": b"3",
                    "b": "9012",
                    "c": ["5678", 1234],
                    "d": {11: "aa", "bb": 22},
                },
                (
                    VerifyTypeError("dict_obj['a']", Union[int, str], b"3"),
                    VerifyTypeError("dict_obj['b']", Literal[1234, "5678"], "9012"),
                    VerifyTypeError("dict_obj['c'][0]", int, "5678"),
                    VerifyTypeError("dict_obj['d']['bb']", int, "bb"),
                    VerifyTypeError("dict_obj['d']['bb']", str, 22),
                ),
            ),
        )
        #                                   (  expected_errors  )  (extra_items_type)
        extra_item_cases: tuple[tuple[dict, tuple[Exception, ...], object], ...] = (
            (
                {
                    "a": "2",
                    "b": "5678",
                    "c": [5678, 1234],
                    "e": 114514,
                },
                (VerifyKeyError("dict_obj", "e", "extra"),),
                NoExtraItems,
            ),
            (
                {
                    "b": 1234,
                    "c": [1234, 5678],
                    "d": {12: "34", 56: "78"},
                    "e": 114514,
                },
                (
                    VerifyKeyError("dict_obj", "a", "missing"),
                    VerifyTypeError("dict_obj['e']", bytes, 114514),
                ),
                bytes,
            ),
        )
        # TypedDict
        for dict_obj, expt_errs, extra_item_type in extra_item_cases:

            class ATypedDict(new_TypedDict, extra_items=extra_item_type):  # type: ignore[call-arg]
                a: int | str
                b: Literal[1234, "5678"]
                c: Required[list[int]]
                d: NotRequired[dict[int, str]]

            self.assertEqual(
                tuple(
                    check_dict(
                        dict_obj,
                        ATypedDict,
                        name="dict_obj",
                    )
                ),
                expt_errs,
            )
            if expt_errs:
                with self.assertRaises((VerifyKeyError, VerifyTypeError)) as cm:
                    assert_dict(
                        dict_obj,
                        ATypedDict,
                        name="dict_obj",
                    )
                self.assertEqual(cm.exception, expt_errs[0])
            else:
                assert_dict(
                    dict_obj,
                    ATypedDict,
                    name="dict_obj",
                )

        for typed_dict in available_typeddict:
            for dict_obj, expt_errs in normal_cases:
                valid = not expt_errs
                with self.subTest(typeddict_source=typed_dict.__module__, valid=valid):

                    class BTypedDict(typed_dict):  # type: ignore[misc, valid-type]
                        a: int | str
                        b: Literal[1234, "5678"]
                        c: Required[list[int]]  # type: ignore[valid-type]
                        d: NotRequired[dict[int, str]]  # type: ignore[valid-type]

                    self.assertEqual(
                        tuple(
                            check_dict(
                                dict_obj,
                                BTypedDict,
                                name="dict_obj",
                            )
                        ),
                        expt_errs,
                    )

                    if valid:
                        assert_dict(
                            dict_obj,
                            BTypedDict,
                            name="dict_obj",
                        )
                    else:
                        with self.assertRaises((VerifyKeyError, VerifyTypeError)) as cm:
                            assert_dict(
                                dict_obj,
                                BTypedDict,
                                name="dict_obj",
                            )
                        self.assertEqual(cm.exception, expt_errs[0])

        # dict
        structure = {
            "a": Union[int, str],
            "b": Literal[1234, "5678"],
            "c": Required[list[int]],
            "d": NotRequired[dict[int, str]],
        }
        for dict_obj, expt_errs in normal_cases:
            self.assertEqual(
                tuple(
                    check_dict(
                        dict_obj,
                        structure,
                        name="dict_obj",
                    )
                ),
                expt_errs,
            )
            if not expt_errs:
                assert_dict(
                    dict_obj,
                    structure,
                    name="dict_obj",
                )
            else:
                with self.assertRaises((VerifyKeyError, VerifyTypeError)) as cm:
                    assert_dict(
                        dict_obj,
                        structure,
                        name="dict_obj",
                    )
                self.assertEqual(cm.exception, expt_errs[0])
