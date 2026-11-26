from __future__ import annotations

import pytest

from jsonargparse import ArgumentError, Namespace, lazy_instance
from jsonargparse.typing import final


@final
class FinalClass:
    def __init__(self, a1: int = 1, a2: float = 2.3):
        self.a1 = a1
        self.a2 = a2


class NotFinalClass:
    def __init__(self, b1: str = "4", b2: FinalClass = lazy_instance(FinalClass, a2=-3.2)):
        self.b1 = b1
        self.b2 = b2


def test_add_class_final(parser):
    parser.add_class_arguments(NotFinalClass, "b")

    assert parser.get_defaults().b.b2 == Namespace(a1=1, a2=-3.2)
    cfg = parser.parse_args(['--b.b2={"a2": 6.7}'])
    assert cfg.b.b2 == Namespace(a1=1, a2=6.7)
    assert cfg == parser.parse_string(parser.dump(cfg))
    cfg = parser.instantiate(cfg)
    assert isinstance(cfg["b"], NotFinalClass)
    assert isinstance(cfg["b"].b2, FinalClass)

    with pytest.raises(ArgumentError, match=r"Group 'b' does not accept option 'b2\.bad'"):
        parser.parse_args(['--b.b2={"bad": "value"}'])
    with pytest.raises(ArgumentError, match=r"""Unable to load config '"bad"'"""):
        parser.parse_args(['--b.b2="bad"'])
    default = FinalClass()
    with pytest.raises(ValueError, match="Expected 'default' to be dict, Namespace, lazy instance or dataclass-like"):
        parser.add_class_arguments(FinalClass, "a", default=default)
