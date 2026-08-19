"""Classes that are only imported inside a TYPE_CHECKING block of another module.

Used by type_checking_stand_ins, which at runtime binds these names to stand-in
values, i.e. the module is deliberately not imported at runtime.
"""


class Hook:
    def __init__(self, name: str = "base"):
        self.name = name


class LogHook(Hook):
    def __init__(self, level: str = "info"):
        super().__init__("log")
        self.level = level


class CacheHook(Hook):
    def __init__(self, size: int = 1):
        super().__init__("cache")
        self.size = size


class Plugin:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
