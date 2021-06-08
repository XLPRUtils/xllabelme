#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Author : 陈坤泽
# @Email  : 877362867@qq.com
# @Date   : 2020/11/29

"""
自动发布库的脚本
"""

from pyxllib.xl import *

# 1 打包发布
subprocess.run('python setup.py sdist')  # 本地生成的.gz可以检查上传的内容
subprocess.run('twine upload dist/*')  # 如果没有twine记得要pip install

# 2 删除发布文件
Dir('dist').delete()
[d.delete() for d in Dir('.').select(r'*.egg-info').subdirs()]
