#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# flake8: noqa

import logging
import re
import sys

from qtpy import QT_VERSION

# 1 官方原版labelme
# __appname__ = "labelme v4.5.7"
# Semantic Versioning 2.0.0: https://semver.org/
# 1. MAJOR version when you make incompatible API changes;
# 2. MINOR version when you add functionality in a backwards-compatible manner;
# 3. PATCH version when you make backwards-compatible bug fixes.

# 每当官方有第2位版本号更新，比如5.2、5.3时，我会尽力做个源码的同步
# 然后我个人功能，会在第3位上自增，比如5.1.2、5.1.3
__version__ = "5.1.2"

# 2 扩展的更灵活的labelme，兼容官方的功能，但有更强的可视化效果，能查看shape的多个属性值
__appname__ = f"xllabelme v{__version__}"

QT4 = QT_VERSION[0] == "4"
QT5 = QT_VERSION[0] == "5"
del QT_VERSION

PY2 = sys.version[0] == "2"
PY3 = sys.version[0] == "3"
del sys

from xllabelme.label_file import LabelFile
from xllabelme import testing
from xllabelme import utils
