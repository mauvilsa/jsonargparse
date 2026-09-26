"""Generation of a JSON Schema that describes the configs accepted by a parser."""

import argparse
import operator
import re
import uuid
from enum import Enum
from types import ModuleType
from typing import Any, Callable, Optional, Tuple, Union

from ._actions import ActionConfigFile, ActionYesNo, _ActionConfigLoad, filter_non_parsing_actions
from ._common import (
    config_schema_key,
    get_generic_origin,
    get_parsing_setting,
    get_unaliased_type,
    is_subclass,
    parser_context,
)
from ._jsonschema import ActionJsonSchema
from ._namespace import Namespace
from ._optionals import get_doc_short_description, pydantic_model_accepts_extra
from ._required import iter_required_keys, restore_suppressed_required
from ._subcommands import ActionSubCommands
from ._typehints import (
    ActionTypeHint,
    callable_origin_types,
    freeze,
    get_all_subclass_paths,
    get_callable_return_type,
    get_namedtuple_annotations,
    get_typed_dict_annotations,
    get_typed_dict_required_keys,
    get_typehint_origin,
    is_namedtuple,
    is_single_subclass_or_closed_type,
    is_single_subclass_type,
    literal_types,
    mapping_origin_types,
    sequence_origin_types,
    tuple_set_origin_types,
    typed_dict_key_qualifiers,
    typed_dict_meta_types,
)
from ._util import NoneType, config_include_key, get_import_path, import_object
from .typing import get_registered_type

schema_uri = "https://json-schema.org/draft/2020-12/schema"

config_schema_key_schema = {
    "type": "string",
    "format": "uri-reference",
    "description": (
        "Location of the JSON Schema that describes this config, so that editors give validation and "
        "autocompletion for it. Ignored when the config is parsed."
    ),
}

include_key_schema = {
    "description": (
        "Path of a config, or a list of them, relative to this config, which are merged before the keys that follow."
    ),
    "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
}

# what the parser of a class gets by default, so it does not make a variant of the class definition
class_parser_defaults = {"skip": set(), "instantiate": True, "fail_untyped": True, "sub_configs": False}

subcommand_description = (
    "Name of the subcommand to run. It can be omitted, in which case it is the only subcommand block "
    "present in the config, or can be given as a command line argument."
)

basic_type_schemas = {
    bool: {"type": "boolean"},
    int: {"type": "integer"},
    float: {"type": "number"},
    str: {"type": "string"},
    NoneType: {"type": "null"},
    dict: {"type": "object"},
    list: {"type": "array"},
    ModuleType: {"type": "string"},
}

uuid_schema = {
    "type": "string",
    "format": "uuid",
    "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
}

restriction_keywords = {
    operator.gt: "exclusiveMinimum",
    operator.ge: "minimum",
    operator.lt: "exclusiveMaximum",
    operator.le: "maximum",
    operator.eq: "const",
}

tuple_origin_types = {Tuple, tuple}
set_origin_types = tuple_set_origin_types - tuple_origin_types


def config_jsonschema(parser) -> dict:
    """Returns a JSON Schema that describes the configs accepted by the given parser."""
    return ParserJsonschema().generate(parser)


def new_object(description: Optional[str] = None, properties: Optional[dict] = None) -> dict:
    schema: dict = {"type": "object", "additionalProperties": False}
    if description:
        schema["description"] = description
    schema["properties"] = dict(properties or {})
    return schema


def class_parser_kwargs(action) -> dict:
    """The kwargs for the parser of a class given in an argument, except the default ones."""
    kwargs = dict(getattr(action, "sub_add_kwargs", None) or {})
    kwargs.pop("linked_targets", None)  # linked parameters are still accepted in configs
    return {k: v for k, v in kwargs.items() if k not in class_parser_defaults or class_parser_defaults[k] != v}


def accepts_extra_keys(parser_or_group) -> bool:
    """Whether a parser or group corresponds to a pydantic model that accepts unknown keys."""
    return pydantic_model_accepts_extra(getattr(parser_or_group, "group_class", None))


def add_required(schema: dict, key: str) -> None:
    required = schema.setdefault("required", [])
    if key not in required:
        required.append(key)


def json_value(value):
    """Converts a default value into its json representation."""
    if isinstance(value, Namespace):
        return json_value(value.as_dict())
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, set):
        return [json_value(v) for v in sorted(value, key=str)]
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    registered = get_registered_type(type(value))
    if registered:  # the same serialization that dump gives, e.g. a path as its string
        return json_value(registered.serializer(value))
    return str(value)


def is_type_only(schema: dict) -> bool:
    return set(schema) == {"type"} and isinstance(schema["type"], str)


unvalidated_schemas: list = [{}, {"type": "object"}]


def is_shape_constrained(schema) -> bool:
    """Whether a schema constrains the shape of an object, i.e. tells apart known from unknown keys."""
    if isinstance(schema, dict):
        if "$ref" in schema or "properties" in schema:
            return True
        return any(is_shape_constrained(value) for value in schema.values())
    if isinstance(schema, list):
        return any(is_shape_constrained(item) for item in schema)
    return False


def anyof_schema(schemas: list) -> dict:
    """Combines subschemas, merging those that only constrain the type."""
    unique: list = []
    for schema in schemas:
        if schema not in unique:
            unique.append(schema)
    if any(is_shape_constrained(s) for s in unique):
        # A subschema that accepts any object would make mistakes in the keys of the shape constrained
        # ones go unnoticed, which is more valuable than accepting exactly what the parser accepts.
        unique = [s for s in unique if s not in unvalidated_schemas]
    types = [s["type"] for s in unique if is_type_only(s)]
    combined = [s for s in unique if not is_type_only(s) and s != {}]
    if types:
        combined.insert(0, {"type": types[0] if len(types) == 1 else types})
    if {} in unique:
        # An unconstrained subschema, e.g. from an Any subtype, already accepts anything. Still, the
        # other subschemas are kept, so that tools have something to describe and complete against.
        combined.append({})
    if len(combined) == 1:
        return combined[0]
    return {"anyOf": combined}


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def replace_refs(schema, renames: dict):
    """Returns a copy of a schema with the references to the renamed definitions changed."""
    if isinstance(schema, dict):
        replaced = {key: replace_refs(value, renames) for key, value in schema.items()}
        if isinstance(schema.get("$ref"), str):
            name = ref_name(schema["$ref"])
            replaced["$ref"] = f"#/$defs/{renames.get(name, name)}"
        return replaced
    if isinstance(schema, list):
        return [replace_refs(item, renames) for item in schema]
    return schema


def collect_ref_names(schema) -> set:
    """Returns the names of the definitions that a schema references."""
    names = set()
    if isinstance(schema, dict):
        if "$ref" in schema:
            names.add(ref_name(schema["$ref"]))
        for value in schema.values():
            names |= collect_ref_names(value)
    elif isinstance(schema, list):
        for item in schema:
            names |= collect_ref_names(item)
    return names


def get_action_description(action) -> Optional[str]:
    help_string = getattr(action, "help", None)
    if not help_string or help_string == argparse.SUPPRESS:
        return None
    if "%(" in help_string:
        params = {k: v for k, v in vars(action).items() if v is not argparse.SUPPRESS}
        params["default"] = json_value(params.get("default"))
        try:
            help_string = help_string % params
        except (KeyError, TypeError, ValueError):
            # Keep the original help text if interpolation fails
            pass
    return help_string


argparse_action_schemas = {
    argparse._StoreTrueAction: {"type": "boolean"},
    argparse._StoreFalseAction: {"type": "boolean"},
    argparse._CountAction: {"type": "integer"},
}

const_action_types = (argparse._StoreConstAction, argparse._AppendConstAction)
append_action_types = (argparse._AppendAction, argparse._AppendConstAction)


def is_const_action(action) -> bool:
    """Whether an action sets a fixed value, excluding the boolean flags which have their own schema."""
    return isinstance(action, const_action_types) and not isinstance(
        action, (argparse._StoreTrueAction, argparse._StoreFalseAction)
    )


def is_append_action(action) -> bool:
    # extend adds the items of each value to the list, so its schema already is the list
    return isinstance(action, append_action_types) and not isinstance(action, argparse._ExtendAction)


def get_dest_consts(parser) -> dict:
    """Returns the values that const actions can set, grouped by dest since several of them can share one."""
    unset_sentinel = get_parsing_setting("unset_sentinel")
    consts: dict = {}
    for action in filter_non_parsing_actions(parser._actions):
        if not is_const_action(action):
            continue
        values = consts.setdefault(action.dest, [])
        candidates = [action.const]
        if isinstance(action, argparse._StoreConstAction):
            candidates.append(action.default)  # not giving the option leaves the default, which is also a valid value
        for value in candidates:
            if value is not unset_sentinel and value is not argparse.SUPPRESS and value not in values:
                values.append(value)
    return consts


def registered_type_schema(typehint, registered) -> dict:
    # types registered with a serializer that is a basic type are dumped as that type, e.g. Decimal as float
    schema = dict(basic_type_schemas.get(registered.serializer, {"type": "string"}))
    restrictions = getattr(typehint, "_restrictions", None)
    if restrictions and getattr(typehint, "_join", "and") == "and":
        for comparison, reference in restrictions:
            keyword = restriction_keywords.get(comparison)
            if keyword:
                schema[keyword] = reference
    elif getattr(typehint, "_regex", None) is not None:
        schema["pattern"] = typehint._regex.pattern
    return schema


def value_type_schema(value_type) -> dict:
    """Schema for the type given to add_argument, for actions that don't have a type hint."""
    if value_type in basic_type_schemas:
        return dict(basic_type_schemas[value_type])
    registered = get_registered_type(value_type)
    if registered:
        return registered_type_schema(value_type, registered)
    return {}


class ParserJsonschema:
    """Builds a JSON Schema from a parser, keeping shared subschemas in ``$defs``."""

    def __init__(self):
        include_enabled = get_parsing_setting("config_include_enabled")
        self.config_keys = [config_schema_key]
        self.defs: dict = {config_schema_key: dict(config_schema_key_schema)}
        if include_enabled:
            self.config_keys.append(config_include_key)
            self.defs[config_include_key] = dict(include_key_schema)
        # configs that include others, or are included, are partial, so their keys can't be required
        self.config_required = not include_enabled
        self.def_types: dict = dict.fromkeys(self.defs)  # reserved, so that classes with these names are renamed
        self.variants: dict = {}  # (base key, frozen kwargs) -> name of the definition
        self.bases: dict = {}  # base key -> (plain name, function that builds the definition for some kwargs)
        self.dest = ""  # full key of the argument being described, which names the variants

    def generate(self, parser) -> dict:
        schema = self.config_object(parser.description)
        with restore_suppressed_required(), parser_context(parent_parser=parser):
            self.add_properties(parser, schema)
            schema = self.merge_variants(schema)
        schema["$defs"] = self.reachable_defs(schema)
        return {"$schema": schema_uri, **schema}

    def config_object(self, description: Optional[str] = None) -> dict:
        """An object that describes a config, which also accepts the keys that are not arguments."""
        return new_object(description, {key: {"$ref": f"#/$defs/{key}"} for key in self.config_keys})

    def add_config_required(self, schema: dict, key: str) -> None:
        if self.config_required:
            add_required(schema, key)

    def reachable_defs(self, schema: dict) -> dict:
        """Discards definitions created for subschemas that ended up not being used."""
        reachable: set = set()
        pending = collect_ref_names(schema)
        while pending:
            name = pending.pop()
            if name not in reachable:
                reachable.add(name)
                pending |= collect_ref_names(self.defs.get(name, {}))
        return {name: definition for name, definition in self.defs.items() if name in reachable}

    # properties

    def add_properties(self, parser, schema: dict, prefix: str = "") -> None:
        required_keys = set(iter_required_keys(parser))
        descriptions = {name: group.title for name, group in parser.groups.items() if group.title}
        extras = {name for name, group in parser.groups.items() if accepts_extra_keys(group)}
        consts = get_dest_consts(parser)
        if accepts_extra_keys(parser):
            schema["additionalProperties"] = True
        for action in filter_non_parsing_actions(parser._actions):
            if isinstance(action, (ActionConfigFile, _ActionConfigLoad)):
                continue
            if isinstance(action, ActionSubCommands):
                self.add_subcommands(action, schema, prefix)
                continue
            self.dest = prefix + action.dest
            required = action.dest in required_keys
            action_schema = self.action_schema(action, required, consts.get(action.dest))
            self.set_dest(schema, action.dest, action_schema, required, descriptions, extras)

    def set_dest(
        self, schema: dict, dest: str, dest_schema: dict, required: bool, descriptions: dict, extras: set
    ) -> None:
        keys = dest.split(".")
        node = schema
        for num, key in enumerate(keys[:-1]):
            properties = node.setdefault("properties", {})
            nested_key = ".".join(keys[: num + 1])
            if properties.get(key, {}).get("type") != "object":
                properties[key] = self.config_object(descriptions.get(nested_key))
                if nested_key in extras:
                    properties[key]["additionalProperties"] = True
            if required:
                self.add_config_required(node, key)
            node = properties[key]
        properties = node.setdefault("properties", {})
        properties[keys[-1]] = dest_schema
        if required:
            self.add_config_required(node, keys[-1])

    def add_subcommands(self, action, schema: dict, prefix: str) -> None:
        # the subcommand key is never required: it is implied when the config has a single subcommand
        # block, and when there are several the chosen one can be given as a command line argument
        # aliases are left out, only the subcommand names are canonical
        subparsers = {n: p for n, p in action._name_parser_map.items() if n == p.subcommand}
        properties = schema.setdefault("properties", {})
        properties[action.dest] = {"enum": list(subparsers), "description": subcommand_description}
        for name, subparser in subparsers.items():
            subcommand_schema = self.config_object(subparser.description)
            self.add_properties(subparser, subcommand_schema, f"{prefix}{name}.")
            properties[name] = subcommand_schema
            if subcommand_schema.get("required"):  # only then is giving the subcommand key unavoidable
                schema.setdefault("allOf", []).append(
                    {
                        "if": {"properties": {action.dest: {"const": name}}, "required": [action.dest]},
                        "then": {"required": [name]},
                    }
                )

    # actions

    def action_schema(self, action, required: bool, consts: Optional[list]) -> dict:
        schema: dict = self.action_type_schema(action, consts)
        if action.nargs in {"+", "*"}:
            schema = {"type": "array", "items": schema}
            if action.nargs == "+":
                schema["minItems"] = 1
        elif isinstance(action.nargs, int) and action.nargs > 1:
            schema = {"type": "array", "items": schema, "minItems": action.nargs, "maxItems": action.nargs}
        if is_append_action(action):  # one value is collected into the list per occurrence of the option
            schema = {"type": "array", "items": schema}
        description = get_action_description(action)
        if description:
            schema["description"] = description
        # a suppressed default leaves no key and an unset one is not a value, so neither is a default to describe
        default = getattr(action, "default", None)
        unset_sentinel = get_parsing_setting("unset_sentinel")
        describe = not required and default is not argparse.SUPPRESS and default is not unset_sentinel
        if describe and (default is not None or self.allows_null(schema)):
            schema["default"] = json_value(default)
        return schema

    def action_type_schema(self, action, consts: Optional[list]) -> dict:
        if action.choices:
            return {"enum": [json_value(choice) for choice in action.choices]}
        if isinstance(action, ActionTypeHint):
            return self.typehint_schema(action._typehint, action)
        if isinstance(action, ActionJsonSchema):
            return dict(action._validator.schema)
        if isinstance(action, ActionYesNo):
            return {"type": "boolean"}
        for action_type, schema in argparse_action_schemas.items():
            if isinstance(action, action_type):
                return dict(schema)
        if consts and is_const_action(action):
            return {"enum": [json_value(const) for const in consts]}
        return value_type_schema(action.type)

    def allows_null(self, schema: dict) -> bool:
        if "$ref" in schema:
            return self.allows_null(self.defs.get(ref_name(schema["$ref"]), {}))
        if "anyOf" in schema:
            return any(self.allows_null(s) for s in schema["anyOf"])
        if "enum" in schema:
            return None in schema["enum"]
        schema_type = schema.get("type")
        if schema_type is None:
            return True
        return schema_type == "null" or (isinstance(schema_type, list) and "null" in schema_type)

    # type hints

    def typehint_schema(self, typehint, action) -> dict:
        typehint = get_unaliased_type(typehint)
        origin = get_typehint_origin(typehint)
        root = origin if origin is not None else typehint  # unsubscripted generics, e.g. list instead of list[int]

        if typehint in {Any, object}:
            return {}
        if origin in typed_dict_key_qualifiers:  # requiredness and mutability come from the TypedDict
            return self.typehint_schema(typehint.__args__[0], action)
        if typehint is uuid.UUID:
            return dict(uuid_schema)
        if typehint in basic_type_schemas:
            return dict(basic_type_schemas[typehint])
        registered = get_registered_type(typehint)
        if registered:
            return registered_type_schema(typehint, registered)
        if is_subclass(typehint, Enum):
            return {"enum": list(typehint.__members__)}
        if type(typehint) in typed_dict_meta_types:
            return self.typed_dict_schema(typehint, action)
        if is_namedtuple(typehint):
            return self.namedtuple_schema(typehint, action)
        if root in literal_types:
            return {"enum": [json_value(arg) for arg in typehint.__args__]}
        if origin is Union:
            return anyof_schema([self.typehint_schema(a, action) for a in typehint.__args__])
        if root is type:
            return {"type": "string"}
        if root in callable_origin_types:
            return self.callable_schema(typehint, action)
        if root in tuple_origin_types:
            return self.tuple_schema(typehint, action)
        if root in set_origin_types:
            return self.items_schema(typehint, action, {"type": "array", "uniqueItems": True})
        if root in sequence_origin_types:
            return self.items_schema(typehint, action, {"type": "array"})
        if root in mapping_origin_types:
            args: tuple = getattr(typehint, "__args__", ())
            if len(args) == 2:
                values_schema = self.typehint_schema(args[1], action)
                if values_schema:
                    return {"type": "object", "additionalProperties": values_schema}
            return {"type": "object"}
        if is_single_subclass_type(typehint, origin):
            return self.class_ref(typehint, action, subclass=True)
        if is_single_subclass_or_closed_type(typehint, origin):
            return self.class_ref(typehint, action, subclass=False)
        return {}

    def items_schema(self, typehint, action, schema: dict) -> dict:
        args = getattr(typehint, "__args__", ())
        if args:
            items = self.typehint_schema(args[0], action)
            if items:
                schema["items"] = items
        return schema

    def tuple_schema(self, typehint, action) -> dict:
        args = getattr(typehint, "__args__", ())
        if not args:
            return {"type": "array"}
        if len(args) == 2 and args[1] is Ellipsis:
            return self.items_schema(typehint, action, {"type": "array"})
        prefix_items = [self.typehint_schema(a, action) for a in args]
        return {
            "type": "array",
            "prefixItems": prefix_items,
            "items": False,
            "minItems": len(prefix_items),
        }

    def callable_schema(self, typehint, action) -> dict:
        schemas = [{"type": "string"}]
        return_type = get_callable_return_type(typehint)
        if return_type and is_single_subclass_type(return_type, get_typehint_origin(return_type)):
            schemas.append(self.class_ref(return_type, action, subclass=True))
        return anyof_schema(schemas)

    def typed_dict_schema(self, typehint, action) -> dict:
        annotations = get_typed_dict_annotations(typehint)
        required_keys = get_typed_dict_required_keys(typehint, annotations)
        schema = new_object(get_doc_short_description(typehint))
        for key, annotation in annotations.items():
            schema["properties"][key] = self.typehint_schema(annotation, action)
            if key in required_keys:
                add_required(schema, key)
        return schema

    def namedtuple_schema(self, typehint, action) -> dict:
        """Describes both forms accepted for a NamedTuple: an object of fields or an array of values."""
        annotations = get_namedtuple_annotations(typehint)
        defaults = typehint._field_defaults
        obj_schema = new_object(get_doc_short_description(typehint))
        for field, annotation in annotations.items():
            obj_schema["properties"][field] = self.typehint_schema(annotation, action)
            if field not in defaults:
                add_required(obj_schema, field)
        array_schema = {
            "type": "array",
            "prefixItems": [obj_schema["properties"][f] for f in annotations],
            "items": False,
            "minItems": len(annotations) - len(defaults),
        }
        return anyof_schema([obj_schema, array_schema])

    # classes

    def class_ref(self, class_type, action, subclass: bool) -> dict:
        class_type = get_generic_origin(class_type)
        build = self.subclass_def if subclass else self.class_parser_schema

        def build_def(kwargs: dict) -> dict:
            return build(class_type, action, kwargs)

        return self.def_ref((subclass, class_type), self.def_name(class_type), class_parser_kwargs(action), build_def)

    def def_ref(self, base_key: tuple, base_name: str, kwargs: dict, build: Callable[[dict], dict]) -> dict:
        """References the definition of a class for the kwargs of its parser, building it the first time.

        With the default kwargs the definition has the plain name. Others are variants, which are named
        by the key where they are first used, e.g. ``Model@model``, and at the end are merged with the
        definitions that ended up being the same.
        """
        key = (base_key, freeze(kwargs))
        if key not in self.variants:
            name = f"{base_name}@{self.dest}" if kwargs else base_name
            self.variants[key] = name
            self.bases[base_key] = (base_name, build)
            self.defs[name] = {}  # placeholder, so that recursive types resolve to the same $ref
            self.defs[name].update(build(kwargs))
        return {"$ref": f"#/$defs/{self.variants[key]}"}

    def merge_variants(self, schema: dict) -> dict:
        """Replaces each variant by the plain definition, or else an earlier variant, that is the same."""
        merged = True
        while merged:
            merged = False
            for (base_key, _), name in list(self.variants.items()):
                base_name, build = self.bases[base_key]
                if name == base_name or name not in self.defs:
                    continue
                self.def_ref(base_key, base_name, {}, build)  # the plain one might not have been needed until now
                for candidate in self.merge_candidates(base_key, name):
                    pairs: set = set()
                    if self.equivalent_defs(name, candidate, pairs):
                        schema = self.merge_defs(schema, pairs)
                        merged = True
                        break
        return schema

    def equivalent_defs(self, name1: str, name2: str, pairs: set) -> bool:
        """Whether two definitions describe the same, where the references can differ in name.

        The pairs being compared are assumed to be equivalent, so that recursive definitions can be compared.
        """
        if name1 == name2 or (name1, name2) in pairs:
            return True
        pairs.add((name1, name2))
        return self.equivalent_schemas(self.defs[name1], self.defs[name2], pairs)

    def equivalent_schemas(self, schema1, schema2, pairs: set) -> bool:
        if isinstance(schema1, dict) and isinstance(schema2, dict):
            if schema1.keys() != schema2.keys():
                return False
            if isinstance(schema1.get("$ref"), str) and isinstance(schema2.get("$ref"), str):
                if not self.equivalent_defs(ref_name(schema1["$ref"]), ref_name(schema2["$ref"]), pairs):
                    return False
            return all(self.equivalent_schemas(schema1[k], schema2[k], pairs) for k in schema1 if k != "$ref")
        if isinstance(schema1, list) and isinstance(schema2, list):
            return len(schema1) == len(schema2) and all(
                self.equivalent_schemas(s1, s2, pairs) for s1, s2 in zip(schema1, schema2)
            )
        return schema1 == schema2

    def merge_defs(self, schema: dict, pairs: set) -> dict:
        """Merges pairs of equivalent definitions, keeping the plain one, or else the one of the candidate."""
        plain_names = {base_name for base_name, _ in self.bases.values()}
        renames: dict = {}

        def resolve(name: str) -> str:
            while name in renames:
                name = renames[name]
            return name

        for name1, name2 in pairs:
            name1, name2 = resolve(name1), resolve(name2)
            if name1 != name2:
                old, new = (name2, name1) if name1 in plain_names else (name1, name2)
                renames[old] = new
                del self.defs[old]
        renames = {old: resolve(old) for old in renames}
        self.variants = {key: renames.get(name, name) for key, name in self.variants.items()}
        self.defs = {name: replace_refs(definition, renames) for name, definition in self.defs.items()}
        return replace_refs(schema, renames)

    def merge_candidates(self, base_key: tuple, name: str) -> list:
        candidates = [self.bases[base_key][0]]
        for (other_base_key, _), other in self.variants.items():
            if other == name:
                break
            if other_base_key == base_key and other not in candidates:
                candidates.append(other)
        return candidates

    def def_name(self, class_type) -> str:
        name = class_type.__name__
        if self.def_types.get(name, class_type) is not class_type:  # a different class with the same name
            name = re.sub(r"\W+", "_", str(get_import_path(class_type)))
        self.def_types.setdefault(name, class_type)
        return name

    def subclass_def(self, class_type, action, kwargs: dict) -> dict:
        """Describes all forms accepted for a subclass: a class path string or a subclass spec."""
        class_paths = get_all_subclass_paths(class_type)
        schemas: list = [{"type": "string"}]  # a class path or a path to a sub-config file
        if class_paths:
            # an object that accepts any class_path would keep tools from suggesting and validating the known ones
            schemas += [self.class_path_ref(path, action, kwargs) for path in class_paths]
        else:  # no known subclass, so any class path is accepted without describing its init args
            schemas.append(self.unknown_class_path_schema())
        return anyof_schema(schemas)

    def class_path_ref(self, class_path: str, action, kwargs: dict) -> dict:
        """References the definition of one class path, named by it so that it can be linked to from outside."""

        def build_def(kwargs: dict) -> dict:
            return self.class_path_schema(class_path, action, kwargs)

        return self.def_ref((None, class_path), class_path, kwargs, build_def)

    def class_path_schema(self, class_path: str, action, kwargs: dict) -> dict:
        schema = self.config_object(get_doc_short_description(import_object(class_path)))
        class_parser = self.get_class_parser(class_path, action, kwargs)
        if class_parser is None:
            init_args_schema = {"type": "object"}
        else:
            init_args_schema = self.parser_schema(class_parser, prefix=f"{self.dest}.init_args.")
        schema["properties"].update({"class_path": {"const": class_path}, "init_args": init_args_schema})
        # resolved parameters are only described in init_args, even though parsing also takes them from dict_kwargs
        if class_parser is None or class_parser._accepted_kwargs[None] is True:
            schema["properties"]["dict_kwargs"] = {"type": "object"}
        if self.config_required:
            # init_args can only be omitted when none of the init parameters is required
            schema["required"] = ["class_path"] + (["init_args"] if init_args_schema.get("required") else [])
        return schema

    def unknown_class_path_schema(self) -> dict:
        """Accepts subclasses whose module is not imported, without describing their init args."""
        schema = self.config_object()
        schema["properties"].update(
            {
                "class_path": {"type": "string"},
                "init_args": {"type": "object"},
                "dict_kwargs": {"type": "object"},
            }
        )
        if self.config_required:
            schema["required"] = ["class_path"]
        return schema

    def get_class_parser(self, class_type, action, kwargs: dict):
        try:
            return ActionTypeHint.get_class_parser(class_type, sub_add_kwargs=kwargs)
        except Exception as ex:
            action.logger.debug(f"Unable to get schema for init args of '{class_type}': {ex}")
            return None

    def parser_schema(self, parser, description: Optional[str] = None, prefix: str = "") -> dict:
        dest = self.dest
        schema = self.config_object(description)
        self.add_properties(parser, schema, prefix)
        self.dest = dest
        return schema

    def class_parser_schema(self, class_type, action, kwargs: dict) -> dict:
        class_parser = self.get_class_parser(class_type, action, kwargs)
        if class_parser is None:
            return {"type": "object"}
        return self.parser_schema(class_parser, get_doc_short_description(class_type), prefix=f"{self.dest}.")
