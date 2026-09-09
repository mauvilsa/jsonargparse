from argparse import Action, _SubParsersAction
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from ._type_checking import ArgumentParser

_suppressed_required_actions: ContextVar[tuple[Action, ...]] = ContextVar("_suppressed_required_actions", default=())


def iter_required_keys(parser: ArgumentParser) -> Iterator[str]:
    """Yields required keys, the ones backed by real argparse actions first."""
    action_keys = [action.dest for action in parser._actions if action.required]
    yield from action_keys
    yield from sorted(parser._extra_required_keys - set(action_keys))


def set_required(parser: ArgumentParser, key_or_action: str | Action, value: bool = True) -> None:
    """Sets required state for either an action-backed or virtual key."""
    action = key_or_action if isinstance(key_or_action, Action) else None
    key: str = action.dest if action is not None else key_or_action  # type: ignore[assignment]
    if action is None:
        action = _find_exact_action(parser, key)
    if action is not None and getattr(action, "dest", None) == key:
        action.required = value
    elif value:
        parser._extra_required_keys.add(key)
    else:
        parser._extra_required_keys.discard(key)


def clear_required(parser: ArgumentParser, key_or_action: str | Action) -> None:
    """Clears required state for either an action-backed or virtual key."""
    set_required(parser, key_or_action, value=False)


def _find_exact_action(parser: ArgumentParser, key: str) -> Action | None:
    for action in parser._actions:
        if getattr(action, "dest", None) == key:
            return action
    return None


@contextmanager
def suppress_required_actions(parser: ArgumentParser):
    """Temporarily disables required enforcement on real argparse actions."""
    suppressed = []
    previously_suppressed = _suppressed_required_actions.get()
    visited = set()

    def visit(subparser):
        if id(subparser) in visited:
            return
        visited.add(id(subparser))
        for action in subparser._actions:
            if action.required:
                suppressed.append(action)
                action.required = False
            if isinstance(action, _SubParsersAction):
                for choice_parser in action.choices.values():
                    visit(choice_parser)

    visit(parser)
    token = _suppressed_required_actions.set(previously_suppressed + tuple(suppressed))
    try:
        yield
    finally:
        _suppressed_required_actions.reset(token)
        for action in reversed(suppressed):
            action.required = True


@contextmanager
def restore_suppressed_required():
    """Temporarily restores required=True for actions suppressed by suppress_required_actions."""
    suppressed = _suppressed_required_actions.get()
    for action in suppressed:
        action.required = True
    try:
        yield
    finally:
        for action in suppressed:
            action.required = False
