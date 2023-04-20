# -*- mode: python -*-
# vim: ft=python

import sys


sys.setrecursionlimit(5000)  # required on Windows


a = Analysis(
    ['xllabelme/__main__.py'],
    pathex=['xllabelme'],
    binaries=[],
    datas=[ # 第一个元素是源文件或文件夹的路径，第二个元素是exe中的目标路径，一般尽量要对称一致
        ('xllabelme/config/default_config.yaml', 'xllabelme/config'),
        ('xllabelme/icons/*', 'xllabelme/icons'),
    ],
    hiddenimports=['cython', 'shapely._geos'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['pandas'],
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='xllabelme',
    debug=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon='xllabelme/icons/icon2.ico',
)
app = BUNDLE(
    exe,
    name='xllabelme.app',
    icon='xllabelme/icons/icon.icns',  # 不考虑mac情况，我先把这个文件删了，这个文件要1M
    bundle_identifier=None,
    info_plist={'NSHighResolutionCapable': 'True'},
)
