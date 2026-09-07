from __future__ import annotations

from dataclasses import dataclass, field
from textwrap import dedent, indent
from typing import Any, Callable, Dict, List, Optional, Union
from unittest.mock import patch

import pytest

from jsonargparse import ArgumentParser
from jsonargparse_tests.conftest import (
    get_parse_args_stdout,
    get_parser_help,
    json_or_yaml_load,
    skip_if_yaml_comments_unavailable,
)

pytestmark = skip_if_yaml_comments_unavailable


def test_dump_comments_not_supported(parser):
    parser.parser_mode = "json"
    parser.add_argument("--op", type=int, default=1)
    cfg = parser.get_defaults()
    with pytest.raises(ValueError, match="Dumping with comments is not supported for format 'json'"):
        parser.dump(cfg, with_comments=True)


def test_dump_comments_missing_ruamel(parser):
    parser.add_argument("--op", type=int, default=1)
    cfg = parser.get_defaults()
    with patch.dict("jsonargparse._loaders_dumpers.dumpers") as dumpers:
        dumpers.pop("yaml_comments", None)
        with pytest.raises(ValueError, match="ruamel.yaml is required for dumping YAML with comments"):
            parser.dump(cfg, with_comments=True)


def test_print_config_comments(print_parser):
    help_str = get_parser_help(print_parser)
    assert "comments," in help_str
    out = get_parse_args_stdout(print_parser, ["--print_config=comments"])
    assert "# cli tool" in out
    assert "# Option v1. (default: 1)" in out
    assert "# Option v2. (default: 2)" in out


def get_dump(parser: ArgumentParser, args: list) -> str:
    cfg = parser.parse_args(args)
    dump = parser.dump(cfg, with_comments=True)
    assert json_or_yaml_load(dump) == json_or_yaml_load(parser.dump(cfg))
    return dump


def block(text: str, depth: int = 0) -> str:
    """Dedents an expected dump block and indents it to the given nested level."""
    return indent(dedent(text), "  " * depth)


class Optimizer:
    def __init__(self, lr: float = 0.1):
        """Base optimizer.

        Args:
            lr: Learning rate.
        """
        self.lr = lr  # pragma: no cover


class SGD(Optimizer):
    def __init__(self, momentum: float = 0.9, **kwargs):
        """Stochastic gradient descent.

        Args:
            momentum: Momentum factor.
        """
        super().__init__(**kwargs)  # pragma: no cover


class NoParams(Optimizer):
    """Optimizer without parameters."""

    def __init__(self):
        pass  # pragma: no cover


class NoDescription(Optimizer):
    def __init__(self, gamma: float = 0.1, **kwargs):
        """
        Args:
            gamma: Decay factor.
        """
        super().__init__(**kwargs)  # pragma: no cover


@dataclass
class Data:
    """Data settings.

    Args:
        path: Path to the data.
        batch_size: Number of samples per batch.
    """

    path: str = "data"
    batch_size: int = 4


@dataclass
class Nested:
    """Nested settings.

    Args:
        data: The data settings.
        seed: Random seed.
    """

    data: Data = field(default_factory=Data)
    seed: int = 1


class Model:
    def __init__(self, optimizer: Optimizer = SGD(), name: str = "model"):
        """A model.

        Args:
            optimizer: The optimizer to use.
            name: Name of the model.
        """


class Trainer:
    def __init__(self, data: Data = Data(), epochs: int = 1):
        """A trainer.

        Args:
            data: The data settings.
            epochs: Number of epochs.
        """


# subclass tests


def test_subclass_init_args(parser):
    parser.add_argument("--optimizer", type=Optimizer, help="The optimizer.")
    dump = get_dump(parser, [f"--optimizer={__name__}.SGD"])
    expected = block(
        f"""
        optimizer:
          class_path: {__name__}.SGD

          # Stochastic gradient descent
          init_args:

            # Momentum factor. (type: float, default: 0.9)
            momentum: 0.9

            # Learning rate. (type: float, default: 0.1)
            lr: 0.1
        """
    )
    assert expected in dump
    assert "# The optimizer. (type: " in dump


def test_subclass_without_init_args(parser):
    parser.add_argument("--optimizer", type=Optimizer, help="The optimizer.")
    dump = get_dump(parser, [f"--optimizer={__name__}.NoParams"])
    assert "init_args" not in dump
    assert "class_path:" in dump


def test_subclass_nested_in_init_args(parser):
    parser.add_argument("--model", type=Model, help="The model.")
    dump = get_dump(parser, [f"--model={__name__}.Model"])
    expected = block(
        f"""
        model:
          class_path: {__name__}.Model

          # A model
          init_args:
        """
    )
    assert expected in dump
    expected = block(
        f"""
        optimizer:
          class_path: {__name__}.SGD

          # Stochastic gradient descent
          init_args:

            # Momentum factor. (type: float, default: 0.9)
            momentum: 0.9

            # Learning rate. (type: float, default: 0.1)
            lr: 0.1

        # Name of the model. (type: str, default: model)
        name: model
        """,
        depth=2,
    )
    assert expected in dump


def test_subclass_in_list(parser):
    parser.add_argument("--optimizers", type=List[Optimizer], help="The optimizers.")
    dump = get_dump(parser, [f"--optimizers=[{__name__}.SGD,{__name__}.Optimizer]"])
    assert "# The optimizers. (type: " in dump
    expected = block(
        f"""
        optimizers:
        - class_path: {__name__}.SGD

          # Stochastic gradient descent
          init_args:

            # Momentum factor. (type: float, default: 0.9)
            momentum: 0.9

            # Learning rate. (type: float, default: 0.1)
            lr: 0.1
        - class_path: {__name__}.Optimizer

          # Base optimizer
          init_args:

            # Learning rate. (type: float, default: 0.1)
            lr: 0.1
        """
    )
    assert expected in dump


def test_subclass_in_nested_list(parser):
    parser.add_argument("--optimizers", type=List[List[Optimizer]], help="The optimizers.")
    dump = get_dump(parser, [f'--optimizers=[[{{"class_path": "{__name__}.SGD", "init_args": {{"momentum": 0.5}}}}]]'])
    expected = block(
        f"""
        optimizers:
        - - class_path: {__name__}.SGD

            # Stochastic gradient descent
            init_args:

              # Momentum factor. (type: float, default: 0.9)
              momentum: 0.5
        """
    )
    assert expected in dump


def test_subclass_in_dict(parser):
    parser.add_argument("--optimizers", type=Dict[str, Optimizer], help="The optimizers.")
    dump = get_dump(parser, [f'--optimizers={{"one": "{__name__}.SGD"}}'])
    expected = block(
        f"""
        optimizers:
          one:
            class_path: {__name__}.SGD

            # Stochastic gradient descent
            init_args:

              # Momentum factor. (type: float, default: 0.9)
              momentum: 0.9

              # Learning rate. (type: float, default: 0.1)
              lr: 0.1
        """
    )
    assert expected in dump


def test_subclass_in_dict_of_lists(parser):
    parser.add_argument("--optimizers", type=Dict[str, List[Optimizer]], help="The optimizers.")
    spec = f'{{"class_path": "{__name__}.SGD", "init_args": {{"momentum": 0.5}}}}'
    dump = get_dump(parser, [f'--optimizers={{"one": [{spec}]}}'])
    expected = block(
        f"""
        optimizers:
          one:
          - class_path: {__name__}.SGD

            # Stochastic gradient descent
            init_args:

              # Momentum factor. (type: float, default: 0.9)
              momentum: 0.5

              # Learning rate. (type: float, default: 0.1)
              lr: 0.1
        """
    )
    assert expected in dump


def test_subclass_without_class_description(parser):
    parser.add_argument("--optimizer", type=Optimizer, help="The optimizer.")
    dump = get_dump(parser, [f"--optimizer={__name__}.NoDescription"])
    expected = block(
        f"""
        optimizer:
          class_path: {__name__}.NoDescription

          # <class '{__name__}.NoDescription'>
          init_args:

            # Decay factor. (type: float, default: 0.1)
            gamma: 0.1

            # Learning rate. (type: float, default: 0.1)
            lr: 0.1
        """
    )
    assert expected in dump


def test_subclass_in_union(parser):
    parser.add_argument("--optimizer", type=Union[int, Optimizer], help="The optimizer.")
    dump = get_dump(parser, [f"--optimizer={__name__}.SGD"])
    assert "# Stochastic gradient descent\n  init_args:" in dump
    assert "# Momentum factor. (type: float, default: 0.9)" in dump


def test_subclass_in_any(parser):
    parser.add_argument("--optimizer", type=Any, help="The optimizer.")
    dump = get_dump(parser, [f'--optimizer={{"class_path": "{__name__}.SGD"}}'])
    assert "# Stochastic gradient descent\n  init_args:" in dump
    assert "# Momentum factor. (type: float, default: 0.9)" in dump


def test_add_subclass_arguments(parser):
    parser.add_subclass_arguments(Optimizer, "optimizer", help="The optimizer.")
    dump = get_dump(parser, [f"--optimizer={__name__}.SGD"])
    assert "# The optimizer. (type: " in dump
    assert "# Stochastic gradient descent\n  init_args:" in dump
    assert "# Momentum factor. (type: float, default: 0.9)" in dump


def test_callable_return_type(parser):
    parser.add_argument("--optimizer", type=Callable[[float], Optimizer], help="The optimizer.")
    dump = get_dump(parser, [f"--optimizer={__name__}.SGD"])
    expected = block(
        f"""
        optimizer:
          class_path: {__name__}.SGD

          # Stochastic gradient descent
          init_args:

            # Learning rate. (type: float, default: 0.1)
            lr: 0.1
        """
    )
    assert expected in dump
    assert "momentum" not in dump


def test_subclass_skipped_init_args(parser):
    parser.add_subclass_arguments(Optimizer, "optimizer", skip={"lr"}, help="The optimizer.")
    dump = get_dump(parser, [f"--optimizer={__name__}.SGD"])
    assert "# Momentum factor. (type: float, default: 0.9)" in dump
    assert "lr" not in dump


def test_unresolvable_class_path(parser):
    parser.add_argument("--data", type=dict, help="Some dict.")
    dump = get_dump(parser, ['--data={"class_path": "not.a.real.Class", "init_args": {"x": 1}}'])
    assert "# Some dict. (type: " in dump
    expected = block(
        """
        data:
          class_path: not.a.real.Class
          init_args:
            x: 1
        """
    )
    assert expected in dump


# dataclass-like tests


def test_dataclass_as_type(parser):
    parser.add_argument("--data", type=Data, help="The data.")
    dump = get_dump(parser, [])
    expected = block(
        """
        # The data
        data:

          # Path to the data. (type: str, default: data)
          path: data

          # Number of samples per batch. (type: int, default: 4)
          batch_size: 4
        """
    )
    assert expected in dump


def test_dataclass_in_optional(parser):
    parser.add_argument("--data", type=Optional[Data], help="The data.")
    dump = get_dump(parser, ["--data={}"])
    expected = block(
        """
        data:

          # Path to the data. (type: str, default: data)
          path: data

          # Number of samples per batch. (type: int, default: 4)
          batch_size: 4
        """
    )
    assert expected in dump
    assert "# The data. (type: " in dump


def test_dataclass_in_list(parser):
    parser.add_argument("--data", type=List[Data], help="The data.")
    dump = get_dump(parser, ["--data=[{}]"])
    expected = block(
        """
        data:
        -
          # Path to the data. (type: str, default: data)
          path: data

          # Number of samples per batch. (type: int, default: 4)
          batch_size: 4
        """
    )
    assert expected in dump


def test_dataclass_in_dict(parser):
    parser.add_argument("--data", type=Dict[str, Data], help="The data.")
    dump = get_dump(parser, ['--data={"one": {}}'])
    expected = block(
        """
        data:
          one:

            # Path to the data. (type: str, default: data)
            path: data

            # Number of samples per batch. (type: int, default: 4)
            batch_size: 4
        """
    )
    assert expected in dump


def test_dataclass_nested_in_dataclass(parser):
    parser.add_argument("--nested", type=Optional[Nested], help="The nested.")
    dump = get_dump(parser, ["--nested={}"])
    expected = block(
        """
        nested:

          # The data settings
          data:

            # Path to the data. (type: str, default: data)
            path: data

            # Number of samples per batch. (type: int, default: 4)
            batch_size: 4

          # Random seed. (type: int, default: 1)
          seed: 1
        """
    )
    assert expected in dump


def test_dataclass_in_subclass_init_args(parser):
    parser.add_argument("--trainer", type=Trainer, help="The trainer.")
    dump = get_dump(parser, [f"--trainer={__name__}.Trainer"])
    expected = block(
        """
        # A trainer
        init_args:

          # The data settings
          data:

            # Path to the data. (type: str, default: data)
            path: data

            # Number of samples per batch. (type: int, default: 4)
            batch_size: 4

          # Number of epochs. (type: int, default: 1)
          epochs: 1
        """,
        depth=1,
    )
    assert expected in dump


# subcommand tests


def test_subcommand_subclass(parser, subparser):
    parser.description = "the tool"
    subparser.description = "fit command"
    subparser.add_argument("--optimizer", type=Optimizer, help="The optimizer.")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("fit", subparser)
    dump = get_dump(parser, ["fit", f"--optimizer={__name__}.SGD"])
    expected = block(
        f"""
        optimizer:
          class_path: {__name__}.SGD

          # Stochastic gradient descent
          init_args:

            # Momentum factor. (type: float, default: 0.9)
            momentum: 0.9

            # Learning rate. (type: float, default: 0.1)
            lr: 0.1
        """,
        depth=1,
    )
    assert dump.startswith("# the tool\n")
    assert "\n# fit command\nfit:\n" in dump
    assert expected in dump


def test_print_config_comments_subclass(parser):
    parser.add_argument("--config", action="config")
    parser.add_argument("--optimizer", type=Optimizer, help="The optimizer.")
    out = get_parse_args_stdout(parser, [f"--optimizer={__name__}.SGD", "--print_config=comments"])
    assert "# Stochastic gradient descent\n  init_args:" in out
    assert "# Momentum factor. (type: float, default: 0.9)" in out
