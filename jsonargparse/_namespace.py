"""Classes and functions related to namespace objects."""

import argparse
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

__all__ = ["Namespace"]


subclasses_disabled_meta_key = "__subclasses_disabled__"
meta_keys = {"__default_config__", "__path__", "__orig__", subclasses_disabled_meta_key}


class NSKeyError(KeyError):
    def __str__(self):
        return str(self.args[0])


def split_key(key: str) -> list[str]:
    return key.split(".")


def split_key_root(key: str) -> list[str]:
    return key.split(".", 1)


def split_key_leaf(key: str) -> list[str]:
    return key.rsplit(".", 1)


def is_meta_key(key: str) -> bool:
    leaf_key = split_key_leaf(key)[-1]
    return leaf_key in meta_keys


def recreate_branches(data, skip_keys=None):
    new_data = data
    if isinstance(data, (Namespace, dict)) and not isinstance(data, OrderedDict):
        new_data = type(data)()
        for key, val in getattr(data, "__dict__", data).items():
            if skip_keys is None or key not in skip_keys:
                new_data[key] = recreate_branches(val, skip_keys)
    elif isinstance(data, list):
        new_data = [recreate_branches(v, skip_keys) for v in data]
    return new_data


class Namespace(argparse.Namespace):
    """Extension of argparse's Namespace to support nesting and subscript access."""

    def __init__(self, *args, **kwargs):
        """Initializer for Namespace instance.

        Instantiating a Namespace with initial values most commonly is done by
        providing keyword arguments, e.g. ``Namespace(name1=value1,
        name2=value2)``. Alternatively a single positional ``Namespace`` or
        ``dict`` object can be given.
        """
        if len(args) == 0:
            super().__init__(**kwargs)
        else:
            if len(kwargs) != 0 or len(args) != 1 or not isinstance(args[0], (argparse.Namespace, dict)):
                raise ValueError("Expected a single positional parameter of type Namespace or dict.")
            for key, val in args[0].items() if isinstance(args[0], dict) else vars(args[0]).items():
                self[key] = val

    def _parse_key(self, key: str) -> tuple[str, "Namespace | None", str]:
        """Parses a key for the nested namespace.

        Args:
            key: The key that is being parsed.

        Returns:
            Tuple with three elements corresponding to:
            - The leaf key.
            - The parent namespace object.
            - The parent namespace key.

        Raises:
            KeyError: When given invalid key.
        """
        if not isinstance(key, str):
            raise NSKeyError(f"Key must be a string, got: {key!r}.")
        if " " in key:
            raise NSKeyError(f'Spaces not allowed in keys: "{key}".')
        key_split = split_key(key)
        if any(k == "" for k in key_split):
            raise NSKeyError(f'Empty nested key: "{key}".')
        key_split = [add_clash_mark(k) for k in key_split]
        leaf_key = key_split[-1]
        parent_ns: Namespace = self
        parent_key = ""
        if len(key_split) > 1:
            parent_key = ".".join(key_split[:-1])
            for subkey in key_split[:-1]:
                if hasattr(parent_ns, subkey) or (isinstance(parent_ns, dict) and subkey in parent_ns):
                    parent_ns = parent_ns[subkey]
                    if parent_ns is not None and not isinstance(parent_ns, (Namespace, dict)):
                        return leaf_key, None, parent_key
                else:
                    return leaf_key, None, parent_key
        return leaf_key, parent_ns, parent_key

    def _parse_required_key(self, key: str) -> tuple[str, "Namespace", str]:
        """Same as _parse_key but raises KeyError if key not found."""
        leaf_key, parent_ns, parent_key = self._parse_key(key)
        if parent_ns is None or not hasattr(parent_ns, leaf_key):
            raise NSKeyError(f'Key "{key}" not found in namespace.')
        return leaf_key, parent_ns, parent_key

    def _create_nested_namespace(self, key: str) -> "Namespace":
        """Creates a nested namespace object.

        Args:
            key: The key where the nested namespace is created.

        Returns:
            The created nested namespace.
        """
        parent_ns = self
        for key in split_key(key):
            if not isinstance(getattr(parent_ns, key, None), Namespace):
                setattr(parent_ns, key, Namespace())
            parent_ns = getattr(parent_ns, key)

        return parent_ns

    def __setattr__(self, name: str, value: Any) -> None:
        """Sets an attribute to a possibly nested namespace."""
        if "." in name:
            self.__setitem__(name, value)
        else:
            super().__setattr__(add_clash_mark(name), value)

    def __setitem__(self, key: str, item: Any) -> None:
        """Sets an item to a possibly nested namespace."""
        leaf_key, parent_ns, parent_key = self._parse_key(key)
        if parent_ns is None:
            parent_ns = self._create_nested_namespace(parent_key)
        if isinstance(parent_ns, dict):
            parent_ns[leaf_key] = item
        else:
            setattr(parent_ns, leaf_key, item)

    def __getitem__(self, key: str) -> Any:
        """Gets an item from a possibly nested namespace."""
        leaf_key, parent_ns, _ = self._parse_required_key(key)
        return getattr(parent_ns, leaf_key)

    def __delitem__(self, key: str) -> None:
        """Deletes an item from a possibly nested namespace."""
        leaf_key, parent_ns, _ = self._parse_key(key)
        del parent_ns.__dict__[leaf_key]

    def __contains__(self, key: str) -> bool:
        """Checks if an item is set possibly in a nested namespace."""
        if not isinstance(key, str):
            return False
        try:
            leaf_key, parent_ns, _ = self._parse_required_key(key)
        except KeyError:
            return False
        return leaf_key in parent_ns.__dict__

    def __bool__(self) -> bool:
        """Returns False if namespace is empty, otherwise True."""
        return bool(self.__dict__)

    def as_dict(self) -> dict[str, Any]:
        """Converts the nested namespaces into nested dictionaries."""
        dic = {}
        for key, val in vars(self).items():
            if isinstance(val, Namespace):
                val = val.as_dict()
            elif isinstance(val, dict) and val != {} and all(isinstance(v, Namespace) for v in val.values()):
                val = {k: v.as_dict() for k, v in val.items()}
            elif isinstance(val, list) and val != [] and all(isinstance(v, Namespace) for v in val):
                val = [v.as_dict() for v in val]
            dic[del_clash_mark(key)] = val
        return dic

    def as_flat(self) -> argparse.Namespace:
        """Converts the nested namespaces into a single argparse flat namespace."""
        flat = argparse.Namespace()
        for key, val in self.items():
            setattr(flat, key, val)
        return flat

    def items(self, branches: bool = False, nested: bool = True) -> Iterator[tuple[str, Any]]:
        """Returns a generator of all leaf (key, value) items, optionally including branches."""
        for key, val in vars(self).items():
            key = del_clash_mark(key)
            if isinstance(val, Namespace):
                if branches:
                    yield key, val
                if not nested:
                    continue
                for subkey, subval in val.items(branches):
                    yield key + "." + del_clash_mark(subkey), subval
            else:
                yield key, val

    def keys(self, branches: bool = False, nested: bool = True) -> Iterator[str]:
        """Returns a generator of all leaf keys, optionally including branches."""
        for key, _ in self.items(branches=branches, nested=nested):
            yield key

    def values(self, branches: bool = False) -> Iterator[Any]:
        """Returns a generator of all leaf values, optionally including branches."""
        for _, val in self.items(branches):
            yield val

    def clone(self, with_meta: bool = True) -> "Namespace":
        """Creates an new copy of the nested namespace.

        Args:
            with_meta: Whether to include metadata keys in the copy.
        """
        return recreate_branches(self, skip_keys=None if with_meta else meta_keys)

    def update(self, value: "Namespace | Any", key: str | None = None, only_unset: bool = False) -> "Namespace":
        """Sets or replaces all items from the given nested namespace.

        Args:
            value: A namespace to update multiple values or other type to set in a single key.
            key: Branch key where to set the value. Required if value is not namespace.
            only_unset: Whether to only set the value if not set in namespace.
        """
        if not isinstance(value, Namespace):
            if not key:
                raise NSKeyError("Key is required if value not a Namespace.")
            if not only_unset or key not in self:
                self[key] = value
        else:
            if key and not isinstance(self.get(key), Namespace):
                self[key] = Namespace()
            prefix = key + "." if key else ""
            for subkey, subval in value.items():
                if not only_unset or prefix + subkey not in self:
                    self[prefix + subkey] = subval
        return self

    def get(self, key: str, default: Any = None) -> Any:
        """Returns the value for the given key if it exists, otherwise the default."""
        try:
            return self[key]
        except (KeyError, TypeError):
            return default

    def pop(self, key: str, default: Any = None) -> Any:
        """Removes the given key and returns its value if it exists, otherwise the default."""
        leaf_key, parent_ns, _ = self._parse_key(key)
        if not parent_ns:
            return default
        return parent_ns.__dict__.pop(leaf_key, default)


clash_names: set[str] = set(dir(Namespace))
clash_mark = "\u200b"


def add_clash_mark(key: str) -> str:
    if key in clash_names:
        key = clash_mark + key
    return key


def del_clash_mark(key: str) -> str:
    if key[0] == clash_mark:
        key = key[1:]
    return key


def expand_dict(data: dict) -> Namespace:
    for k, v in data.items():
        if isinstance(v, dict) and all(isinstance(k, str) for k in v):
            data[k] = expand_dict(v)
        elif isinstance(v, list):
            for nn, vv in enumerate(v):
                if isinstance(vv, dict) and all(isinstance(k, str) for k in vv):
                    data[k][nn] = expand_dict(vv)
    return Namespace(**data)


def dict_to_namespace(data: dict[str, Any]) -> Namespace:
    data = recreate_branches(data)
    return expand_dict(data)


def remove_meta(cfg: Namespace | dict):
    if cfg:
        cfg = recreate_branches(cfg, skip_keys=meta_keys)
    return cfg


def get_non_meta_sorted_keys(namespace: Namespace) -> list[str]:
    keys = [k for k in namespace.keys(branches=True) if not is_meta_key(k)]
    keys.sort(key=lambda x: -len(split_key(x)))
    return keys


def get_value_and_parent(namespace: Namespace, key: str) -> tuple[Any, Namespace, str]:
    leaf_key, parent_ns, _ = namespace._parse_required_key(key)
    return parent_ns[leaf_key], parent_ns, leaf_key
