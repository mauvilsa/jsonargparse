from __future__ import annotations

import argparse
import platform

import pytest

from jsonargparse import Namespace
from jsonargparse._namespace import NSKeyError, meta_keys

skip_if_no_setattr_insertion_order = pytest.mark.skipif(
    platform.python_implementation() != "CPython",
    reason="requires __setattr__ insertion order",
)


def test_shallow_dot_set_get():
    ns = Namespace()
    ns.a = 1
    assert 1 == ns.a
    assert ns == Namespace(a=1)


def test_shallow_attr_set_get_del():
    ns = Namespace()
    setattr(ns, "a", 1)
    assert 1 == getattr(ns, "a")
    assert ns == Namespace(a=1)
    delattr(ns, "a")
    with pytest.raises(AttributeError):
        getattr(ns, "a")


def test_shallow_item_set_get_del():
    ns = Namespace()
    ns["a"] = 1
    assert 1 == ns["a"]
    assert ns == Namespace(a=1)
    del ns["a"]
    with pytest.raises(KeyError):
        ns["a"]


def test_nested_item_set_get():
    ns = Namespace()
    ns["x.y.z"] = 1
    assert Namespace(x=Namespace(y=Namespace(z=1))) == ns
    assert 1 == ns["x.y.z"]
    assert 1 == ns["x"]["y"]["z"]
    assert Namespace(z=1) == ns["x.y"]
    assert Namespace(z=1) == ns["x"]["y"]
    ns["x.y"] = 2
    assert 2 == ns["x.y"]


def test_nested_item_set_del():
    ns = Namespace()
    ns["x.y"] = 1
    assert Namespace(x=Namespace(y=1)) == ns
    del ns["x.y"]
    assert Namespace(x=Namespace()) == ns


def test_get():
    ns = Namespace()
    ns["x.y"] = 1
    assert 1 == ns.get("x.y")
    assert Namespace(y=1) == ns.get("x")
    assert 2 == ns.get("z", 2)
    assert ns.get("z") is None


@pytest.mark.parametrize("key", [None, True, False, 1, 2.3])
def test_get_non_str_key(key):
    ns = Namespace()
    assert ns.get(key) is None
    assert ns.get(key, "abc") == "abc"


def test_set_item_nested_dict():
    ns = Namespace(d={"a": 1})
    ns["d.b"] = 2
    assert 2 == ns["d"]["b"]


@pytest.mark.parametrize("key", [None, True, False, 1, 2.3])
def test_contains_non_str_key(key):
    ns = Namespace()
    assert key not in ns


def test_pop():
    ns = Namespace()
    ns["x.y.z"] = 1
    assert 1 == ns.pop("x.y.z")
    assert ns == Namespace(x=Namespace(y=Namespace()))


def test_nested_item_invalid_set():
    ns = Namespace()
    with pytest.raises(KeyError):
        ns["x."] = 1
    with pytest.raises(KeyError):
        ns["x .y"] = 2


def test_nested_key_in():
    ns = Namespace()
    ns["x.y.z"] = 1
    assert "x" in ns
    assert "x.y" in ns
    assert "x.y.z" in ns
    assert "a" not in ns
    assert "x.a" not in ns
    assert "x.y.a" not in ns
    assert "x.y.z.a" not in ns
    assert "x..y" not in ns
    assert 123 not in ns


@skip_if_no_setattr_insertion_order
def test_items_generator():
    ns = Namespace()
    ns["a"] = 1
    ns["b.c"] = 2
    ns["b.d"] = 3
    ns["p.q.r"] = {"x": 4, "y": 5}
    items = list(ns.items())
    assert items == [("a", 1), ("b.c", 2), ("b.d", 3), ("p.q.r", {"x": 4, "y": 5})]


@skip_if_no_setattr_insertion_order
def test_keys_generator():
    ns = Namespace()
    ns["a"] = 1
    ns["b.c"] = 2
    ns["b.d"] = 3
    ns["p.q.r"] = {"x": 4, "y": 5}
    keys = list(ns.keys())
    assert keys == ["a", "b.c", "b.d", "p.q.r"]


@skip_if_no_setattr_insertion_order
def test_values_generator():
    ns = Namespace()
    ns["a"] = 1
    ns["b.c"] = 2
    ns["b.d"] = 3
    ns["p.q.r"] = {"x": 4, "y": 5}
    values = list(ns.values())
    assert values == [1, 2, 3, {"x": 4, "y": 5}]


def test_non_str_keys():
    ns = Namespace(a=Namespace(b=Namespace(c=1)))
    with pytest.raises(NSKeyError, match="Key must be a string, got: 0"):
        [x for x in ns.a.b]


def test_namespace_from_dict():
    dic = {"a": 1, "b": {"c": 2}}
    ns = Namespace(dic)
    assert ns == Namespace(a=1, b={"c": 2})


def test_as_dict():
    ns = Namespace()
    ns["w"] = 1
    ns["x.y"] = 2
    ns["x.z"] = 3
    ns["p"] = {"q": Namespace(r=4)}
    assert ns.as_dict() == {"w": 1, "x": {"y": 2, "z": 3}, "p": {"q": {"r": 4}}}
    assert Namespace().as_dict() == {}


def test_as_dict_namespaces_mixed_with_other_values():
    ns = Namespace()
    ns["a"] = {"n": Namespace(r=1), "s": "str"}
    ns["b"] = [Namespace(r=2), "str"]
    ns["c"] = {"deep": [{"n": Namespace(r=3)}]}
    assert ns.as_dict() == {
        "a": {"n": {"r": 1}, "s": "str"},
        "b": [{"r": 2}, "str"],
        "c": {"deep": [{"n": {"r": 3}}]},
    }


def test_as_flat():
    ns = Namespace()
    ns["w"] = 1
    ns["x.y.z"] = 2
    flat = ns.as_flat()
    assert isinstance(flat, argparse.Namespace)
    assert vars(flat) == {"w": 1, "x.y.z": 2}


def test_clone():
    ns = Namespace()
    pqr = {"x": 4, "y": 5}
    ns["a"] = 1
    ns["p.q.r"] = pqr
    assert ns["p.q.r"] is pqr
    assert ns.clone() == ns
    assert ns.clone()["p.q.r"] is not pqr
    assert ns.clone()["p.q"] is not ns["p.q"]


def test_update_shallow():
    ns_from = Namespace(a=1, b=None)
    ns_to = Namespace(a=None, b=2, c=3)
    ns_to.update(ns_from)
    assert ns_to == Namespace(a=1, b=None, c=3)


def test_update_invalid():
    ns = Namespace()
    with pytest.raises(KeyError):
        ns.update(123)


def test_init_from_argparse_flat_namespace():
    argparse_ns = argparse.Namespace()
    setattr(argparse_ns, "w", 0)
    setattr(argparse_ns, "x.y.a", 1)
    setattr(argparse_ns, "x.y.b", 2)
    setattr(argparse_ns, "z.c", 3)
    ns = Namespace(argparse_ns)
    assert ns == Namespace(w=0, x=Namespace(y=Namespace(a=1, b=2)), z=Namespace(c=3))


def test_init_invalid():
    with pytest.raises(ValueError):
        Namespace(1)
    with pytest.raises(ValueError):
        Namespace(argparse.Namespace(), x=1)


def test_use_for_kwargs():
    def func(a=1, b=2, c=3):
        return a, b, c

    kwargs = Namespace(a=4, c=5)
    val = func(**kwargs)
    assert val == (4, 2, 5)


def test_shallow_clashing_keys():
    ns = Namespace()
    assert "get" not in ns
    exec("ns.get = 1")
    assert "get" in ns
    assert ns.get("get") == 1
    assert dict(ns.items()) == {"get": 1}
    ns["pop"] = 2
    assert ns["pop"] == 2
    assert ns.as_dict() == {"get": 1, "pop": 2}
    assert ns.pop("get") == 1
    assert dict(**ns) == {"pop": 2}
    assert ns.as_flat() == argparse.Namespace(pop=2)
    del ns["pop"]
    assert ns == Namespace()
    assert Namespace(update=3).as_dict() == {"update": 3}


def test_leaf_clashing_keys():
    ns = Namespace()
    ns["x.get"] = 1
    assert "x.get" in ns
    assert ns.get("x.get") == 1
    assert ns["x.get"] == 1
    assert ns["x"]["get"] == 1
    assert ns.as_dict() == {"x": {"get": 1}}
    assert dict(ns.items()) == {"x.get": 1}
    assert str(ns.as_flat()) == "Namespace(**{'x.get': 1})"
    assert ns.pop("x.get") == 1
    assert ns.get("x.get") is None


def test_shallow_branch_clashing_keys():
    ns = Namespace(get=Namespace(x=2))
    assert "get.x" in ns
    assert ns.get("get.x") == 2
    assert ns["get.x"] == 2
    assert ns["get"] == Namespace(x=2)
    assert ns.as_dict() == {"get": {"x": 2}}
    assert dict(ns.items()) == {"get.x": 2}
    assert ns.pop("get.x") == 2


def test_nested_branch_clashing_keys():
    ns = Namespace()
    ns["x.get.y"] = 3
    assert "x.get.y" in ns
    assert ns.get("x.get.y") == 3
    assert ns.as_dict() == {"x": {"get": {"y": 3}}}
    assert ns.pop("x.get.y") == 3


@pytest.mark.parametrize("meta_key", meta_keys)
def test_add_argument_meta_key_error(meta_key, parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument(meta_key)
    ctx.match(f'"{meta_key}" not allowed')


def test_items_branches_nested():
    ns = Namespace()
    ns["a.b"] = 1
    ns["a.c"] = 2
    ns["d"] = 3

    items = list(ns.items(branches=True))
    assert items == [("a", Namespace(b=1, c=2)), ("a.b", 1), ("a.c", 2), ("d", 3)]

    items = list(ns.items(branches=True, nested=False))
    assert items == [("a", Namespace(b=1, c=2)), ("d", 3)]

    items = list(ns.items(nested=False))
    assert items == [("d", 3)]


def test_keys_branches_nested():
    ns = Namespace()
    ns["a.b"] = 1
    ns["a.c"] = 2
    ns["d"] = 3

    keys = list(ns.keys(branches=True))
    assert keys == ["a", "a.b", "a.c", "d"]

    keys = list(ns.keys(branches=True, nested=False))
    assert keys == ["a", "d"]

    keys = list(ns.keys(nested=False))
    assert keys == ["d"]
