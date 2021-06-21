#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# flake8: noqa

import logging
import re
import sys

from qtpy import QT_VERSION

# 1 官方原版labelme
# __appname__ = "labelme v4.5.7"
__version__ = "4.5.7"

# 2 扩展的更灵活的labelme，兼容官方的功能，但有更强的可视化效果，能查看shape的多个属性值
__appname__ = "xllabelme v1.8"

__appname = re.sub(r' v[\d\.]+$', '', __appname__)

QT4 = QT_VERSION[0] == "4"
QT5 = QT_VERSION[0] == "5"
del QT_VERSION

PY2 = sys.version[0] == "2"
PY3 = sys.version[0] == "3"
del sys

from xllabelme.label_file import LabelFile
from xllabelme import testing
from xllabelme import utils
