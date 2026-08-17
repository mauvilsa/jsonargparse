from __future__ import annotations

from typing import List
from unittest.mock import patch

import pytest

from jsonargparse import Namespace, set_parsing_settings
from jsonargparse._optionals import attrs_support
from jsonargparse_tests.conftest import get_parser_help, skip_if_docstring_parser_unavailable

if attrs_support:
    import attrs

    @attrs.define
    class AttrsData:
        p1: float
        p2: str = "-"

    @attrs.define
    class AttrsSubData(AttrsData):
        p3: int = 3

    @attrs.define
    class AttrsFieldFactory:
        p1: List[str] = attrs.field(factory=lambda: ["one", "two"])

    @attrs.define
    class AttrsFieldInitFalse:
        p1: dict = attrs.field(init=False)

        def __attrs_post_init__(self):
            self.p1 = {}

    @attrs.define
    class AttrsSubField:
        p1: str = "-"
        p2: int = 0

    @attrs.define
    class AttrsWithNestedDefaultDataclass:
        p1: float
        subfield: AttrsSubField = attrs.field(factory=AttrsSubField)

    @attrs.define
    class AttrsWithNestedDataclassNoDefault:
        p1: float
        subfield: AttrsSubField

    @attrs.define
    class AttrsAlias:
        p1: int = attrs.field(default=1, alias="why")
        _p2: str = "-"

    @attrs.define
    class AttrsAttrDocsBase:
        p1: str = "-"
        """p1 description"""

    @attrs.define
    class AttrsAttrDocsSub(AttrsAttrDocsBase):
        p2: int = 2
        """p2 description"""


@pytest.mark.skipif(not attrs_support, reason="attrs package is required")
class TestAttrs:
    def test_define(self, parser):
        parser.add_argument("--data", type=AttrsData)
        defaults = parser.get_defaults()
        assert Namespace(p1=None, p2="-") == defaults.data
        cfg = parser.parse_args(["--data.p1=0.2", "--data.p2=x"])
        assert Namespace(p1=0.2, p2="x") == cfg.data

    def test_subclass(self, parser):
        parser.add_argument("--data", type=AttrsSubData)
        defaults = parser.get_defaults()
        assert Namespace(p1=None, p2="-", p3=3) == defaults.data

    def test_field_factory(self, parser):
        parser.add_argument("--data", type=AttrsFieldFactory)
        cfg1 = parser.parse_args([])
        cfg2 = parser.parse_args([])
        assert cfg1.data.p1 == ["one", "two"]
        assert cfg1.data.p1 == cfg2.data.p1
        assert cfg1.data.p1 is not cfg2.data.p1

    def test_field_init_false(self, parser):
        parser.add_argument("--data", type=AttrsFieldInitFalse)
        cfg = parser.parse_args([])
        help_str = get_parser_help(parser)
        assert "--data.p1" not in help_str
        assert cfg == Namespace()
        init = parser.instantiate(cfg)
        assert init.data.p1 == {}

    def test_nested_with_default(self, parser):
        parser.add_argument("--data", type=AttrsWithNestedDefaultDataclass)
        cfg = parser.parse_args(["--data.p1=1.23"])
        assert cfg.data == Namespace(p1=1.23, subfield=Namespace(p1="-", p2=0))

    def test_nested_without_default(self, parser):
        parser.add_argument("--data", type=AttrsWithNestedDataclassNoDefault)
        cfg = parser.parse_args(["--data.p1=1.23"])
        assert cfg.data == Namespace(p1=1.23, subfield=Namespace(p1="-", p2=0))

    @skip_if_docstring_parser_unavailable
    @patch.dict("jsonargparse._optionals._docstring_parse_options")
    def test_attribute_docstrings_inherited(self, parser):
        set_parsing_settings(docstring_parse_attribute_docstrings=True)
        parser.add_class_arguments(AttrsAttrDocsSub, "d")
        help_str = get_parser_help(parser)
        assert "p1 description (type: str, default: -)" in help_str
        assert "p2 description (type: int, default: 2)" in help_str

    def test_field_alias(self, parser):
        parser.add_class_arguments(AttrsAlias, "d")
        help_str = get_parser_help(parser)
        assert "--d.why" in help_str
        assert "--d.p1" not in help_str
        cfg = parser.parse_args(["--d.why=2"])
        assert cfg.d == Namespace(why=2, p2="-")
        init = parser.instantiate(cfg)
        assert init.d == AttrsAlias(2, "-")

    def test_private_attribute_init_name(self, parser):
        parser.add_class_arguments(AttrsAlias, "d")
        cfg = parser.parse_args(["--d.p2=x"])
        assert cfg.d == Namespace(why=1, p2="x")
        init = parser.instantiate(cfg)
        assert init.d._p2 == "x"
