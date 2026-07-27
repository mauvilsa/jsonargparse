from __future__ import annotations  # keep

from typing import TYPE_CHECKING, TypedDict

from jsonargparse._typehints import Required

if TYPE_CHECKING:  # pragma: no cover
    from decimal import Decimal

    class TypeCheckingOnlyInDifferentModule:
        pass


class SameNameInBothModules:
    defined_in = "base"


class DifferentModuleTypeCheckingTypedDict(TypedDict, total=False):
    """Base for a TypedDict that is inherited in a different module.

    The postponed annotations below are only resolvable from the names of the
    TYPE_CHECKING block of this module, ``only_in_base`` in particular not being
    available anywhere else. Inherited in test_postponed_annotations.
    """

    name: Required[str]
    amount: Decimal
    only_in_base: TypeCheckingOnlyInDifferentModule
    same_name_in_base: SameNameInBothModules
