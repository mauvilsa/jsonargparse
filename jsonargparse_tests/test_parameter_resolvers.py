from __future__ import annotations

import calendar
import inspect
import xml.dom
from calendar import Calendar
from functools import partialmethod
from random import shuffle
from typing import Any, Callable, Dict, List, Optional, Union
from unittest.mock import patch

import pytest

from jsonargparse import Namespace, class_from_function
from jsonargparse._optionals import docstring_parser_support
from jsonargparse._parameter_resolvers import ConditionalDefault, is_lambda
from jsonargparse._parameter_resolvers import get_signature_parameters as get_params
from jsonargparse_tests.conftest import BaseClass, capture_logs, source_unavailable, wrap_fn


class ClassA:
    def __init__(self, ka1: float = 1.2, ka2: bool = False, **kwargs):
        """
        Args:
            ka1: help for ka1
            ka2: help for ka2
        """

    def method_a(self, pma1: int, pma2: float, kma1: str = "x"):
        """
        Args:
            pma1: help for pma1
            pma2: help for pma2
            kma1: help for kma1
        """

    partial_method_a = partialmethod(method_a, pma1=1, pma2=0.5)


class ClassB(ClassA):
    def __init__(self, pkb1: str, kb1: int = 3, kb2: str = "4", **kwargs):
        """
        Args:
            pkb1: help for pkb1
            kb1: help for kb1
            kb2: help for kb2
        """
        super().__init__(ka2=True, **kwargs)  # pragma: no cover

    @classmethod
    def make(cls, pkcm1: str, kcm1: bool = False, **kws):
        """
        Args:
            pkcm1: help for pkcm1
            kcm1: help for kcm1
        """
        return ClassB(pkcm1, **kws)  # pragma: no cover


class ClassC(ClassB):
    def __init__(self, kc1: str = "-", **kargs):
        """
        Args:
            kc1: help for kc1
        """
        super().__init__(**kargs)  # pragma: no cover


class ClassN:
    def __init__(self, kn1: int = 1, **kargs):  # pragma: no cover
        """
        Args:
            kn1: help for kn1
        """
        self.kn2: int  # verify (though questionable stylistically) that value-less AnnAssign doesn't break resolution


class Param:
    p1: int = 2


class ClassD(Param, ClassA):
    def __init__(self, kd1: bool = False, **kwargs):
        """
        Args:
            kd1: help for kd1
        """
        super().__init__(**kwargs)  # pragma: no cover

    def method_d(self, pmd1: int, *args, kmd1: int = 2, **kws):
        """
        Args:
            pmd1: help for pmd1
            kmd1: help for kmd1
        """
        return super().method_a(*args, **kws)  # pragma: no cover

    @staticmethod
    def staticmethod_d(ksmd1: str = "z", **kw):
        """
        Args:
            ksmd1: help for ksmd1
        """
        return function_return_class_c(ksmd1, k2=2, **kw)  # pragma: no cover


class ClassE1:
    """
    Args:
        ke1: help for ke1
    """

    def __init__(self, ke1: int = 1, **kwargs):
        self._kwd = dict(k2=3, **kwargs)  # pragma: no cover

    def start(self):
        return function_no_args_no_kwargs(**self._kwd)  # pragma: no cover


class ClassE2:
    def __init__(self, **kwargs):  # pragma: no cover
        self._kwd = dict(**kwargs)
        self.fn = lambda **kw: None

    def start(self):
        return self.fn(**self._kwd)  # pragma: no cover


class AttributeLocalImport1:
    def __init__(self, **kwargs):
        self._kwd = dict(**kwargs)  # pragma: no cover

    def run(self):  # pragma: no cover
        from jsonargparse import set_loader

        return set_loader(**self._kwd)


class AttributeLocalImport2:
    def __init__(self, **kwargs):
        self._kwd = dict(**kwargs)  # pragma: no cover

    def run(self):  # pragma: no cover
        import jsonargparse as ja

        return ja.set_loader(**self._kwd)


class AttributeLocalImport3:
    def __init__(self, **kwargs):
        self._kwd = dict(**kwargs)  # pragma: no cover

    def run(self):  # pragma: no cover
        from jsonargparse import set_loader

        return set_loader(**self._kwd)


class AttributeLocalImport4:
    def __init__(self, **kwargs):
        self._kwd = dict(**kwargs)  # pragma: no cover

    def run(self):  # pragma: no cover
        from jsonargparse import set_loader as sl

        return sl(**self._kwd)


class AttributeLocalImportFailure:
    def __init__(self, **kwargs):
        self._kwd = dict(**kwargs)  # pragma: no cover

    def run(self):  # pragma: no cover
        from jsonargparse import does_not_exist

        return does_not_exist(**self._kwd)


class ClassF1:
    def __init__(self, **kw):  # pragma: no cover
        self._ini = dict(k2=4)
        self._ini.update(**kw)

    def _run(self):
        self.staticmethod_f(**self._ini)  # pragma: no cover

    @staticmethod
    def staticmethod_f(ksmf1: str = "w", **kw):
        """
        Args:
            ksmf1: help for ksmf1
        """
        return function_no_args_no_kwargs(**kw)  # pragma: no cover


class ClassF2:
    def __init__(self, **kw):  # pragma: no cover
        self._ini: Dict[str, Any] = {"k2": 4}
        self._ini.update(**kw)

    def _run(self):
        self.staticmethod_f(**self._ini)  # pragma: no cover

    @staticmethod
    def staticmethod_f(ksmf1: str = "w", **kw):
        """
        Args:
            ksmf1: help for ksmf1
        """
        return function_no_args_no_kwargs(**kw)  # pragma: no cover


class ClassG:
    def __init__(self, func: str, **kws):
        """
        Args:
            func: help for func
        """
        self.func = func
        self.kws = kws

    def _run(self):
        if self.func == "1":
            self.method1(**self.kws)
        elif self.func == "2":
            self.method2(**self.kws)

    def method1(self, kmg1: int = 1, kmg2: str = "-", kmg3: bool = True):
        """
        Args:
            kmg1: help for kmg1
            kmg2: help for kmg2
            kmg3: help for kmg3
        """
        self.called = "method1"

    def method2(self, kmg1: int = 1, kmg2: float = 2.3, kmg3: bool = False, kmg4: int = 4):
        """
        Args:
            kmg1: help for kmg1
            kmg3: help for kmg3
            kmg4: help for kmg4
        """
        self.called = "method2"


class ClassM1:
    def __init__(self, km1: int = 1):
        """
        Args:
            km1: help for km1
        """


class ClassM2(ClassM1):
    def __init__(self, km2: int = 2, **kwargs):
        """
        Args:
            km2: help for km2
        """
        super().__init__(**kwargs)  # pragma: no cover


class ClassM3(ClassM1):
    def __init__(self, km3: int = 0, **kwargs):
        """
        Args:
            km3: help for km3
        """
        super().__init__(**kwargs)  # pragma: no cover


class ClassM4(ClassM2, ClassM3):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # pragma: no cover


class ClassM5(ClassM2):
    def __init__(self, km5: int = 5, **kwargs):
        """
        Args:
            km5: help for km5
        """
        super(ClassM2, self).__init__(**kwargs)  # pragma: no cover


class ClassP:
    def __init__(self, kp1: int = 1, **kw):
        """
        Args:
            kp1: help for kp1
        """
        self._kw = kw  # pragma: no cover

    @property
    def data(self):
        return function_no_args_no_kwargs(**self._kw)  # pragma: no cover


class ClassS1:
    def __init__(self, ks1: int = 2, **kw):
        """
        Args:
            ks1: help for ks1
        """
        self.ks1 = ks1  # pragma: no cover

    @classmethod
    def classmethod_s(cls, **kwargs):
        return cls(**kwargs)  # pragma: no cover


class ClassS2:
    def __init__(self, **kwargs):
        self.kwargs = kwargs  # pragma: no cover

    def run_classmethod_s(self):
        return ClassS1.classmethod_s(**self.kwargs)  # pragma: no cover


class ClassU1:
    def __init__(self, k1: int = 1, **ka):  # pragma: no cover
        data = Namespace()
        data.ka = ka


class ClassU2:
    def __init__(self, k1: int = 1, **ka):
        self.method_u2(ka=ka)  # pragma: no cover

    def method_u2(self, ka: dict):
        pass  # pragma: no cover


class ClassU3(ClassU1, ClassU2):
    def __init__(self, **ka):  # pragma: no cover
        super(ClassA, self).__init__(**ka)  # pylint: disable=bad-super-call


class ClassU4:
    def __init__(self, k1: int = 1, **ka):
        self._ka = ka  # pragma: no cover


class ClassU5:
    def __init__(self, **kws):
        self.kws = kws  # pragma: no cover

    def _run(self):
        self.method1(kws=self.kws)  # pragma: no cover

    def method1(self, kws: dict):
        pass  # pragma: no cover


class Optimizer:
    def __init__(self, params: List[int]):
        self.params = params  # pragma: no cover


class SGD(Optimizer):
    def __init__(self, params: List[int], lr: float, **kwargs):  # pragma: no cover
        super().__init__(params, **kwargs)
        self.lr = lr


class ClassInstanceDefaults:
    def __init__(
        self,
        layers: int,
        number: float = 0.2,
        elements: Callable[..., List[int]] = lambda *a: list(a),
        node: Callable[[], xml.dom.Node] = lambda: xml.dom.Node(),
        cal1: Calendar = Calendar(firstweekday=1),
        cal2: Calendar = calendar.TextCalendar(2),
        opt1: Callable[[List[int]], Optimizer] = lambda p: SGD(p, lr=0.01),
        opt2: Callable[[List[int]], Optimizer] = lambda p: SGD(p, 0.02),
        opt3: Callable[[List[int]], Optimizer] = lambda p, lr=0.1: SGD(p, lr=lr),  # type: ignore[misc]
        opt4: Callable[[List[int]], Optimizer] = lambda p: Calendar(firstweekday=3),  # type: ignore[assignment,return-value]
        **kwargs,
    ):
        """
        Args:
            layers: help for layers
            number: help for number
            elements: help for elements
            node: help for node
            cal1: help for cal1
            cal2: help for cal2
            opt1: help for opt1
            opt2: help for opt2
            opt3: help for opt3
            opt4: help for opt4
        """


GLOBAL_CONSTANT = False


class ConditionalGlobalConstant(BaseClass):
    @wrap_fn
    def __init__(self, **kwargs):  # pragma: no cover
        super().__init__()
        kwargs.get("p1", "x")
        if GLOBAL_CONSTANT:
            kwargs.get("p2", "y")
        else:
            kwargs.get("p3", "z")


def function_no_args_no_kwargs(pk1: str, k2: int = 1):
    """
    Args:
        pk1: help for pk1
        k2: help for k2
    """


def function_with_kwargs(k1: bool = True, **kwds):
    """
    Args:
        k1: help for k1
    """
    return function_no_args_no_kwargs(**kwds)  # pragma: no cover


def function_return_class_c(pk1: str, k2: int = 1, **ka):
    """
    Args:
        pk1: help for pk1
        k2: help for k2
    """
    return ClassC(pk1, kb1=k2, **ka)  # pragma: no cover


def function_make_class_b(*args, k1: str = "-", **kwargs):
    """
    Args:
        k1: help for k1
    """
    return ClassB.make(*args, **kwargs)  # pragma: no cover


def function_pop_get_from_kwargs(kn1: int = 0, **kw):  # pragma: no cover
    """
    Args:
        k2: help for k2
        kn1: help for kn1
        kn2: help for kn2
        kn3: help for kn3
        kn4: help for kn4
    """
    kw.pop("k2", 2)
    kw.pop("kn2", 0.5)
    kw.get("kn3", {})
    kw.pop("kn4", [1])
    kw.get("pk1", "")
    function_no_args_no_kwargs(**kw)
    kw.pop("pk1", "")


def function_pop_get_conditional(p1: str, **kw):  # pragma: no cover
    """
    Args:
        p1: help for p1
        p2: help for p2
        p3: help for p3
    """
    kw.get("p3", "x")
    if p1 == "a":
        kw.pop("p2", None)
    elif p1 == "b":
        kw.pop("p2", 3)
        kw.get("p3", "y")


def function_with_bug(**kws):  # pragma: no cover
    return does_not_exist(**kws)  # noqa: F821


def function_unsupported_component(**kwds):  # pragma: no cover
    select = ["Text", "HTML", ""]
    shuffle(select)
    getattr(calendar, f"{select[0]}Calendar")(**kwds)


def function_module_class(**kwds):  # pragma: no cover
    return calendar.Calendar(**kwds)


def function_local_import(**kwds):  # pragma: no cover
    from jsonargparse import set_loader

    return set_loader(**kwds)


constant_boolean_1 = True
constant_boolean_2 = False


def function_constant_boolean(**kwargs):  # pragma: no cover
    if constant_boolean_1:
        return function_with_kwargs(**kwargs)
    elif not constant_boolean_2:
        return function_with_kwargs(k1=False, **kwargs)


def function_invalid_type(param: "invalid:" = 1):  # type: ignore # noqa: F722
    """
    Args:
        param: help for param
    """


def cond_1(kc: int = 1, kn0: str = "x", kn1: str = "-"):
    """
    Args:
        kc: help for kc
        kn1: help for kn1
    """


def cond_2(kc: int = 1, kn2: bool = True):
    """
    Args:
        kn2: help for kn2
    """


def cond_3(kc: int = 1, kn3: int = 2, kn4: float = 0.1):
    """
    Args:
        kn3: help for kn3
        kn4: help for kn4
    """


def conditional_calls(**kwargs):  # pragma: no cover
    if "kn1" in kwargs:
        cond_1(kn0="y", **kwargs)
    elif "kn2" in kwargs:
        cond_2(**kwargs)
    else:
        cond_3(**kwargs)


def function_optional_callable(p1: Optional[Callable] = None, **kw):
    """
    Args:
        p1: help for p1
    """
    function_no_args_no_kwargs(**kw)  # pragma: no cover


def assert_params(params, expected, origins={}, help=True):
    assert expected == [p.name for p in params]
    if help:
        docs = [f"help for {p.name}" for p in params] if docstring_parser_support else [None] * len(params)
        assert docs == [p.doc for p in params]
    assert all(isinstance(params[n].default, ConditionalDefault) for n in origins)
    param_origins = {
        n: [o.split(f"{__name__}.", 1)[1] for o in p.origin] for n, p in enumerate(params) if p.origin is not None
    }
    assert param_origins == origins


# class parameters tests


def test_get_params_class_no_inheritance_unused_kwargs():
    params = get_params(ClassA)
    assert_params(params, ["ka1", "ka2"])
    with source_unavailable():
        assert params == get_params(ClassA)


def test_get_params_class_with_inheritance_hard_coded_kwargs():
    assert_params(get_params(ClassB), ["pkb1", "kb1", "kb2", "ka1"])
    with source_unavailable():
        assert_params(get_params(ClassB), ["pkb1", "kb1", "kb2", "ka1", "ka2"])


def test_get_params_class_with_inheritance_unused_args():
    assert_params(get_params(ClassC), ["kc1", "pkb1", "kb1", "kb2", "ka1"])
    with source_unavailable():
        assert_params(get_params(ClassC), ["kc1", "pkb1", "kb1", "kb2", "ka1", "ka2"])


def test_get_params_class_with_valueless_init_ann():
    assert_params(get_params(ClassN), ["kn1"])
    with source_unavailable():
        assert_params(get_params(ClassN), ["kn1"])


def test_get_params_class_with_inheritance_parent_without_init():
    params = get_params(ClassD)
    assert_params(params, ["kd1", "ka1", "ka2"])
    with source_unavailable():
        assert params == get_params(ClassD)


def test_get_params_class_with_kwargs_in_dict_attribute():
    assert_params(get_params(ClassE1), ["ke1", "pk1", "k2"])
    assert_params(get_params(ClassE2), [])
    assert_params(get_params(ClassF1), ["ksmf1", "pk1", "k2"])
    assert_params(get_params(ClassF2), ["ksmf1", "pk1", "k2"])
    with source_unavailable():
        assert_params(get_params(ClassE1), ["ke1"])
        assert_params(get_params(ClassF1), [])


@pytest.mark.parametrize(
    "cls",
    [AttributeLocalImport1, AttributeLocalImport2, AttributeLocalImport3, AttributeLocalImport4],
)
def test_get_params_local_import_with_kwargs_in_dict_attribute(cls):
    params = get_params(cls)
    assert ["mode", "loader_fn", "exceptions", "json_superset"] == [p.name for p in params]
    with source_unavailable():
        assert get_params(cls) == []


def test_get_params_local_import_failure_with_kwargs_in_dict_attribute(logger):
    with capture_logs(logger) as logs:
        params = get_params(AttributeLocalImportFailure, logger=logger)
    assert params == []
    assert "Failed to get 'does_not_exist'" in logs.getvalue()


def test_get_params_class_kwargs_in_attr_method_conditioned_on_arg():
    params = get_params(ClassG)
    assert_params(
        params,
        ["func", "kmg1", "kmg2", "kmg3", "kmg4"],
        {
            2: ["ClassG._run:3", "ClassG._run:5"],
            3: ["ClassG._run:3", "ClassG._run:5"],
            4: ["ClassG._run:5"],
        },
    )
    assert params[2].annotation == Union[str, float]
    assert str(params[2].default) == "Conditional<ast-resolver> {-, 2.3}"
    assert str(params[3].default) == "Conditional<ast-resolver> {True, False}"
    assert str(params[4].default) == "Conditional<ast-resolver> {4, NOT_ACCEPTED}"
    with source_unavailable():
        assert_params(get_params(ClassG), ["func"])


def test_get_params_method_resolution_order():
    assert_params(get_params(ClassM4), ["km2", "km3", "km1"])
    with source_unavailable():
        assert_params(get_params(ClassM4), ["km2", "km3", "km1"])


def test_get_params_nonimmediate_method_resolution_order():
    assert_params(get_params(ClassM5), ["km5", "km1"])
    with source_unavailable():
        assert_params(get_params(ClassM5), ["km5", "km2", "km1"])


def test_get_params_kwargs_use_in_property():
    assert_params(get_params(ClassP), ["kp1", "pk1", "k2"])
    with source_unavailable():
        assert_params(get_params(ClassP), ["kp1"])


def test_get_params_class_from_function():
    class_a = class_from_function(function_return_class_c, ClassC)
    params = get_params(class_a)
    assert_params(params, ["pk1", "k2", "pkb1", "kb2", "ka1"])
    with source_unavailable():
        params = get_params(class_a)
        assert_params(params, ["pk1", "k2"])


class ClassMethod:
    def __init__(self, pi: int):
        self.pi = pi  # pragma: no cover

    @classmethod
    def from_str(cls, ps: str):
        return cls(1)  # pragma: no cover

    @classmethod
    def from_untyped(cls, pu):
        return cls(2)  # pragma: no cover


ClassMethodFromStr = class_from_function(ClassMethod.from_str, ClassMethod, name="ClassMethodFromStr")
ClassMethodFromUntyped = class_from_function(ClassMethod.from_untyped, ClassMethod, name="ClassMethodFromUntyped")


def test_get_params_class_from_function_classmethod_typed():
    params = get_params(ClassMethodFromStr)
    assert [p.name for p in params] == ["ps"]
    assert params[0].annotation is str


def test_get_params_class_from_function_classmethod_untyped():
    params = get_params(ClassMethodFromUntyped)
    assert [p.name for p in params] == ["pu"]
    assert params[0].annotation is inspect._empty


def test_get_params_class_instance_defaults(subtests):
    params = get_params(ClassInstanceDefaults)
    assert_params(
        params,
        [
            "layers",
            "number",
            "elements",
            "node",
            "cal1",
            "cal2",
            "opt1",
            "opt2",
            "opt3",
            "opt4",
        ],
    )
    with subtests.test("unmodified defaults"):
        assert params[0].default is inspect._empty
        assert params[1].default == 0.2
        assert is_lambda(params[2].default)
    with subtests.test("supported defaults"):
        assert params[3].default == dict(class_path="xml.dom.Node")
        assert params[4].default == dict(class_path="calendar.Calendar", init_args=dict(firstweekday=1))
        assert params[6].default == dict(class_path=f"{__name__}.SGD", init_args=dict(lr=0.01))
    with subtests.test("unsupported defaults"):
        assert isinstance(params[5].default, calendar.TextCalendar)
        assert is_lambda(params[7].default)
        assert is_lambda(params[9].default)
    with subtests.test("invalid defaults"):
        assert is_lambda(params[8].default)


def test_get_params_class_conditional_global_constant():
    params = get_params(ConditionalGlobalConstant)
    assert ["p1", "p3"] == [p.name for p in params]
    assert "GLOBAL_CONSTANT" not in ConditionalGlobalConstant.__init__.__globals__


# class method parameters tests


def test_get_params_method_no_args_no_kwargs():
    params = get_params(ClassA, "method_a")
    assert_params(params, ["pma1", "pma2", "kma1"])
    with source_unavailable():
        assert params == get_params(ClassA, "method_a")


def test_get_params_method_call_super_method():
    assert_params(get_params(ClassD, "method_d"), ["pmd1", "kmd1", "pma1", "pma2", "kma1"])
    with source_unavailable():
        assert_params(get_params(ClassD, "method_d"), ["pmd1", "kmd1"])


def test_get_params_staticmethod_call_function_return_class_c():
    params = get_params(ClassD.staticmethod_d)
    assert params == get_params(ClassD, "staticmethod_d")
    assert_params(params, ["ksmd1", "pkb1", "kb2", "ka1"])
    with source_unavailable():
        params = get_params(ClassD.staticmethod_d)
        assert params == get_params(ClassD, "staticmethod_d")
        assert_params(params, ["ksmd1"])


def test_get_params_classmethod_make_class():
    assert_params(get_params(ClassB.make), ["pkcm1", "kcm1", "kb1", "kb2", "ka1"])
    with source_unavailable():
        assert_params(get_params(ClassB.make), ["pkcm1", "kcm1"])


def test_get_params_classmethod_instantiate_from_cls():
    assert_params(get_params(ClassS1, "classmethod_s"), ["ks1"])
    assert_params(get_params(ClassS2), ["ks1"])
    with source_unavailable():
        assert_params(get_params(ClassS1, "classmethod_s"), [])


# function method parameters tests


def test_get_params_function_no_args_no_kwargs():
    params = get_params(function_no_args_no_kwargs)
    assert ["pk1", "k2"] == [p.name for p in params]
    with source_unavailable():
        assert params == get_params(function_no_args_no_kwargs)


def test_get_params_function_with_kwargs():
    assert_params(get_params(function_with_kwargs), ["k1", "pk1", "k2"])
    with source_unavailable():
        assert_params(get_params(function_with_kwargs), ["k1"])


def test_get_params_function_return_class_c():
    assert_params(get_params(function_return_class_c), ["pk1", "k2", "pkb1", "kb2", "ka1"])
    with source_unavailable():
        assert_params(get_params(function_return_class_c), ["pk1", "k2"])


def test_get_params_function_call_classmethod():
    assert_params(get_params(function_make_class_b), ["k1", "pkcm1", "kcm1", "kb1", "kb2", "ka1"])
    with source_unavailable():
        assert_params(get_params(function_make_class_b), ["k1"])


def test_get_params_function_pop_get_from_kwargs(logger):
    with capture_logs(logger) as logs:
        params = get_params(function_pop_get_from_kwargs, logger=logger)
    assert str(params[1].default) == "Conditional<ast-resolver> {2, 1}"
    assert_params(
        params,
        ["kn1", "k2", "kn2", "kn3", "kn4", "pk1"],
        {1: ["function_pop_get_from_kwargs:10", "function_pop_get_from_kwargs:15"]},
    )
    assert "unsupported kwargs pop/get default" in logs.getvalue()
    with source_unavailable():
        assert_params(get_params(function_pop_get_from_kwargs), ["kn1"])


def test_get_params_function_pop_get_conditional():
    params = get_params(function_pop_get_conditional)
    assert str(params[1].default) == "Conditional<ast-resolver> {x, y}"
    assert str(params[2].default) == "Conditional<ast-resolver> {None, 3}"
    assert_params(
        params,
        ["p1", "p3", "p2"],
        {
            1: ["function_pop_get_conditional:8", "function_pop_get_conditional:13"],
            2: ["function_pop_get_conditional:10", "function_pop_get_conditional:12"],
        },
    )


def test_get_params_function_module_class():
    params = get_params(function_module_class)
    assert ["firstweekday"] == [p.name for p in params]


def test_get_params_function_local_import():
    params = get_params(function_local_import)
    assert ["mode", "loader_fn", "exceptions", "json_superset"] == [p.name for p in params]


def function_nested_module_attr(**kwargs):  # pragma: no cover
    import xml.dom.minidom

    return xml.dom.minidom.parseString(**kwargs)


def test_get_params_function_nested_module_attr():
    params = get_params(function_nested_module_attr)
    assert "string" in [p.name for p in params]
    with source_unavailable():
        assert [] == get_params(function_nested_module_attr)


class ClassNestedModuleAttr:
    def __init__(self, **kwargs):  # pragma: no cover
        import xml.dom.minidom

        self.doc = xml.dom.minidom.parseString(**kwargs)


def test_get_params_class_nested_module_attr():
    params = get_params(ClassNestedModuleAttr)
    assert "string" in [p.name for p in params]
    with source_unavailable():
        assert [] == get_params(ClassNestedModuleAttr)


class ClassNestedLocalFromImport:
    def __init__(self, **kwargs):  # pragma: no cover
        from xml.dom import minidom

        self.result = minidom.parseString(**kwargs)


def test_get_params_class_nested_local_from_import():
    params = get_params(ClassNestedLocalFromImport)
    assert "string" in [p.name for p in params]
    with source_unavailable():
        assert [] == get_params(ClassNestedLocalFromImport)


def test_get_params_function_constant_boolean():
    assert_params(get_params(function_constant_boolean), ["k1", "pk1", "k2"])
    with patch.dict(function_constant_boolean.__globals__, {"constant_boolean_1": False}):
        assert_params(get_params(function_constant_boolean), ["pk1", "k2"])
        with patch.dict(function_constant_boolean.__globals__, {"constant_boolean_2": True}):
            assert get_params(function_constant_boolean) == []


def test_get_params_function_invalid_type(logger):
    with capture_logs(logger):
        params = get_params(function_invalid_type, logger=logger)
    assert_params(params, ["param"])
    assert params[0].annotation.replace("'", "") == "invalid:"


def test_conditional_calls_kwargs():
    assert_params(
        get_params(conditional_calls),
        ["kc", "kn1", "kn2", "kn3", "kn4"],
        {
            1: ["conditional_calls:3"],
            2: ["conditional_calls:5"],
            3: ["conditional_calls:7"],
            4: ["conditional_calls:7"],
        },
    )
    with source_unavailable():
        assert get_params(conditional_calls) == []


def test_get_params_optional_callable():
    assert_params(get_params(function_optional_callable), ["p1", "pk1", "k2"])


def func_several_params(p1: int = 1, p2: int = 2, p3: int = 3, p4: int = 4):
    pass  # pragma: no cover


def func_given_kwargs(p: int, **kwargs):  # pragma: no cover
    func_several_params(p2=0, **kwargs)
    func_several_params(p4=0, **kwargs)


def test_get_params_given_kwargs():
    assert_params(get_params(func_given_kwargs), ["p", "p1", "p3"], help=False)


def test_get_params_some_ignored():
    with patch.dict(
        "jsonargparse._parameter_resolvers.ignore_params", {f"{__name__}.func_several_params": {"p2", "p3"}}
    ):
        assert_params(get_params(func_several_params), ["p1", "p4"], help=False)
    with patch.dict("jsonargparse._parameter_resolvers.ignore_params", {f"{__name__}.func_given_kwargs": {"p3"}}):
        assert_params(get_params(func_given_kwargs), ["p", "p1"], help=False)


def test_partialmethod():
    ClassA.partial_method_a = partialmethod(ClassA.method_a, pma1=1, pma2=0.5)
    assert_params(get_params(ClassA, "partial_method_a"), ["pma1", "pma2", "kma1"])
    with source_unavailable():
        assert_params(get_params(ClassA, "partial_method_a"), ["pma1", "pma2", "kma1"])


# unsupported cases


def test_unsupported_component(logger):
    with capture_logs(logger) as logs:
        assert [] == get_params(function_unsupported_component, logger=logger)
    assert "not supported" in logs.getvalue()


def test_unsupported_type_of_assign(logger):
    with capture_logs(logger) as logs:
        get_params(ClassU1, logger=logger)
    assert "unsupported type of assign" in logs.getvalue()


def test_unsupported_kwarg_as_keyword(logger):
    with capture_logs(logger) as logs:
        get_params(ClassU2, logger=logger)
    assert "kwargs given as keyword parameter not supported" in logs.getvalue()


def test_unsupported_super_with_arbitrary_params(logger):
    with capture_logs(logger) as logs:
        get_params(ClassU3, logger=logger)
    assert "unsupported super parameters" in logs.getvalue()


def test_unsupported_self_attr_not_found_in_members(logger):
    with capture_logs(logger) as logs:
        get_params(ClassU4, logger=logger)
    assert "did not find use of self._ka in members of" in logs.getvalue()


def test_unsupported_kwarg_attr_as_keyword(logger):
    with capture_logs(logger) as logs:
        get_params(ClassU5, logger=logger)
    assert "kwargs attribute given as keyword parameter not supported" in logs.getvalue()


def test_get_params_non_existent_call(logger):
    with capture_logs(logger) as logs:
        assert [] == get_params(function_with_bug, logger=logger)
    assert "does_not_exist" in logs.getvalue()


# failure cases


def test_get_params_failures():
    pytest.raises(ValueError, lambda: get_params("invalid"))
    pytest.raises(ValueError, lambda: get_params(Param, "p1"))
    pytest.raises(AttributeError, lambda: get_params(Param, "p2"))
