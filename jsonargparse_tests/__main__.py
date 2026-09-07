"""Run all unit tests in package."""

import os
import sys
import warnings
from pathlib import Path

import pytest


def run_tests():
    filter_action = "default"
    warnings.simplefilter(filter_action)
    os.environ["PYTHONWARNINGS"] = filter_action
    testing_package = Path(__file__).parent
    exit_code = pytest.main(["-v", "-s", f"--rootdir={testing_package.parent}", "--pyargs", str(testing_package)])
    if exit_code != 0:
        sys.exit(True)


if __name__ == "__main__":
    run_tests()
