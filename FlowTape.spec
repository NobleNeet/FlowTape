# Build inside the target OS with: pyinstaller FlowTape.spec
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['flowtape/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[('flowtape/dom.js', 'flowtape'), ('flowtape/observer.js', 'flowtape')],
    hiddenimports=['flowtape.ui', 'flowtape.qt_playback'] + collect_submodules('selenium.webdriver.common.devtools'),
    hookspath=[],
    runtime_hooks=[],
    excludes=['pytest', '_pytest', 'IPython'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FlowTape', console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FlowTape')
