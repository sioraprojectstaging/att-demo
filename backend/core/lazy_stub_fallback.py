"""
Keep scikit-image importable on Vercel.

scikit-image (used by insightface for face alignment) loads its submodules
lazily through `lazy_loader.attach_stub`, which parses the package's
`__init__.pyi` type stub at import time. Vercel's Python bundler drops `.pyi`
files, so on Vercel the import fails with:

    Cannot load imports from non-existent stub '.../skimage/__init__.pyi'

core/lazy_stubs/ holds copies of those stubs (scikit-image 0.25.2, saved as
.pyi.txt so the bundler keeps them). When a stub is missing, the copy is
written to a temp dir and handed to the original attach_stub.

If scikit-image is upgraded, refresh the copies:
    for f in $(cd venv/lib/python3.12/site-packages && find skimage -name "__init__.pyi"); do
        cp venv/lib/python3.12/site-packages/$f core/lazy_stubs/$(dirname $f | tr / .).pyi.txt
    done
"""

import os
import tempfile
from pathlib import Path

STUB_DIR = Path(__file__).resolve().parent / 'lazy_stubs'


def install():
    import lazy_loader

    if getattr(lazy_loader, '_siora_stub_fallback', False):
        return
    original = lazy_loader.attach_stub

    def attach_stub(package_name, filename):
        stub = filename if filename.endswith('i') else f'{os.path.splitext(filename)[0]}.pyi'
        if not os.path.exists(stub):
            vendored = STUB_DIR / f'{package_name}.pyi.txt'
            if vendored.exists():
                target = Path(tempfile.gettempdir()) / 'siora-lazy-stubs' / f'{package_name}.pyi'
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    partial = target.with_suffix(f'.{os.getpid()}.tmp')
                    partial.write_text(vendored.read_text())
                    os.replace(partial, target)
                return original(package_name, str(target))
        return original(package_name, filename)

    lazy_loader.attach_stub = attach_stub
    lazy_loader._siora_stub_fallback = True
