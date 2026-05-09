import os

import numpy
from setuptools import Extension, setup

NUMPY_INCLUDE = numpy.get_include()

SKIP_EXT_BUILD = os.environ.get("QLIB_SKIP_EXT_BUILD", "").lower() in {"1", "true", "yes"}

ext_modules = []
if not SKIP_EXT_BUILD:
    ext_modules = [
        Extension(
            "qlib.data._libs.rolling",
            ["qlib/data/_libs/rolling.pyx"],
            language="c++",
            include_dirs=[NUMPY_INCLUDE],
        ),
        Extension(
            "qlib.data._libs.expanding",
            ["qlib/data/_libs/expanding.pyx"],
            language="c++",
            include_dirs=[NUMPY_INCLUDE],
        ),
    ]


setup(ext_modules=ext_modules)
