import os

if "JSONARGPARSE_OMEGACONF_FULL_TEST" in os.environ:
    import warnings

    from jsonargparse._loaders_dumpers import loaders, set_omegaconf_loader

    set_omegaconf_loader()
    if "omegaconf" in loaders:
        loaders["yaml"] = loaders["omegaconf"]
        warnings.warn("Running all tests with omegaconf as the yaml loader.")

__version__ = "4.50.0"
