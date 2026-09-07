"""Action to support jsonschemas."""

import os

from ._actions import _is_action_value_list
from ._common import Action, parser_context
from ._loaders_dumpers import get_loader_exceptions, load_value
from ._namespace import remove_meta
from ._optionals import (
    get_jsonschema_exceptions,
    import_jsonschema,
    pyyaml_available,
)
from ._util import parse_value_or_config

__all__ = ["ActionJsonSchema"]


class ActionJsonSchema(Action):
    """Action to parse option as JSON validated by a JSON Schema."""

    def __init__(self, schema: str | dict | None = None, sub_config: bool = True, with_meta: bool = True, **kwargs):
        """Initializer for ActionJsonSchema instance.

        Args:
            schema: Schema to validate values against.
            sub_config: Whether to try to load JSON from path.
            with_meta: Whether to include metadata.

        Raises:
            ValueError: If a parameter is invalid.
            jsonschema.exceptions.SchemaError: If the schema is invalid.
        """
        if schema is not None:
            if isinstance(schema, str):
                mode = "yaml" if pyyaml_available else "json"
                with parser_context(load_value_mode=mode):
                    try:
                        schema = load_value(schema)
                    except get_loader_exceptions(mode) as ex:
                        raise ValueError(f"Problems parsing schema: {ex}") from ex
            jsonvalidator = import_jsonschema("ActionJsonSchema")[1]
            jsonvalidator.check_schema(schema)
            self._validator = self._extend_jsonvalidator_with_default(jsonvalidator)(schema)
            self._sub_config = sub_config
            self._with_meta = with_meta
        elif "_validator" not in kwargs:
            raise ValueError("Expected schema keyword argument.")
        else:
            self._validator = kwargs.pop("_validator")
            self._sub_config = kwargs.pop("_sub_config")
            self._with_meta = kwargs.pop("_with_meta")
            super().__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        """Parses an argument validating against the corresponding JSON Schema.

        Raises:
            TypeError: If the argument is not valid.
        """
        if len(args) == 0:
            kwargs["_validator"] = self._validator
            kwargs["_sub_config"] = self._sub_config
            kwargs["_with_meta"] = self._with_meta
            if "help" in kwargs and isinstance(kwargs["help"], str) and "%s" in kwargs["help"]:
                import json

                kwargs["help"] = kwargs["help"] % json.dumps(self._validator.schema, sort_keys=True)
            class_type = kwargs.pop("_class_type", ActionJsonSchema)
            return class_type(**kwargs)
        val = self._check_type(args[2])
        if not self._with_meta:
            val = remove_meta(val)
        setattr(args[1], self.dest, val)
        return None

    def _check_type(self, value):
        islist = _is_action_value_list(self)
        if not islist:
            value = [value]
        for num, val in enumerate(value):
            try:
                val, fpath = parse_value_or_config(val, enable_path=self._sub_config)
                path_meta = val.pop("__path__") if isinstance(val, dict) and "__path__" in val else None
                self._validator.validate(val)
                if path_meta is not None:
                    val["__path__"] = path_meta
                if isinstance(val, dict) and fpath is not None:
                    val["__path__"] = fpath
                value[num] = val
            except (TypeError, ValueError) + get_jsonschema_exceptions() + get_loader_exceptions() as ex:
                elem = "" if not islist else " element " + str(num + 1)
                raise TypeError(f'Parser key "{self.dest}"{elem}: {ex}') from ex
        return value if islist else value[0]

    @staticmethod
    def _extend_jsonvalidator_with_default(validator_class):
        """Extends a json schema validator so that it fills in default values."""
        validate_properties = validator_class.VALIDATORS["properties"]

        def set_defaults(validator, properties, instance, schema):
            valid = True
            for validation in validate_properties(validator, properties, instance, schema):
                if isinstance(validation, jsonschema.exceptions.ValidationError):
                    valid = False
                yield validation
            if valid:
                for prop, subschema in properties.items():
                    if "default" in subschema:
                        instance.setdefault(prop, subschema["default"])

        jsonschema = import_jsonschema("ActionJsonSchema")[0]
        return jsonschema.validators.extend(validator_class, {"properties": set_defaults})

    def completer(self, prefix, **kwargs):
        """Used by argcomplete, validates value and shows expected type."""
        if chr(int(os.environ["COMP_TYPE"])) == "?":
            from ._completions import argcomplete_warn_redraw_prompt

            try:
                if prefix.strip() == "":
                    raise ValueError()
                self._validator.validate(load_value(prefix))
                msg = "value already valid, "
            except (ValueError,) + get_jsonschema_exceptions() + get_loader_exceptions():
                msg = "value not yet valid, "
            else:
                import json

                schema = json.dumps(self._validator.schema, indent=2, sort_keys=True).replace("\n", "\n  ")
                msg += f"required to be valid according to schema:\n  {schema}\n"
            return argcomplete_warn_redraw_prompt(prefix, msg)
