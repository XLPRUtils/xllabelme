# -*- mode: python -*-
# vim: ft=python

import sys


sys.setrecursionlimit(5000)  # required on Windows


a = Analysis(
    ['xllabelme/__main__.py'],
    pathex=['xllabelme'],
    binaries=[],
    datas=[
        ('xllabelme/config/default_config.yaml', 'xllabelme/config'),
        ('xllabelme/icons/*', 'xllabelme/icons'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    icon='xllabelme/icons/icon.ico',
)
app = BUNDLE(
    exe,
    name='xllabelme.app',
    icon='xllabelme/icons/icon.icns',
    bundle_identifier=None,
    info_plist={'NSHighResolutionCapable': 'True'},
)
