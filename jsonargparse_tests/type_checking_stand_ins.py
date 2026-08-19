"""Module whose annotations are evaluated against TYPE_CHECKING stand-ins.

Deliberately without ``from __future__ import annotations``, so that the
annotations below are evaluated when the module is imported, that is, against
the values bound by the ``else`` block. The four names cover the ways in which
a stand-in is written in the wild.
"""

from dataclasses import dataclass
from types import UnionType
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from jsonargparse_tests.type_checking_classes import CacheHook, Hook, LogHook, Plugin
else:
    Hook = Any
    Plugin = object

    class LogHook:
        """Dummy class that stands in for the real one."""

    locals()["CacheHook"] = object


class Agent:
    def __init__(self, hooks: Optional[list[Hook]] = None, plugin: Optional[Plugin] = None):
        """
        Args:
            hooks: List of hooks to run.
            plugin: Plugin to use.
        """
        self.hooks = hooks
        self.plugin = plugin


def function_stand_ins(log: Optional[LogHook] = None, cache: Optional[CacheHook] = None):
    return log, cache  # pragma: no cover


def function_type_expression(hint: Optional[UnionType] = None):
    return hint  # pragma: no cover


def function_genuine_any(value: Any = None, data: Optional[dict[str, Any]] = None):
    return value, data  # pragma: no cover


@dataclass
class AgentConfig:
    """Dataclass with a field annotated with a stand-in."""

    hook: Optional[Hook] = None
    name: str = "config"
