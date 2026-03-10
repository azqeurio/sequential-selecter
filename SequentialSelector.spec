# -*- mode: python ; coding: utf-8 -*-
"""
Compatibility wrapper.
Use `ssc.spec` for Windows builds and `ssc_macos.spec` for macOS builds.
"""

import os

_BASE = os.path.dirname(os.path.abspath(__file__))
_WINDOWS_SPEC = os.path.join(_BASE, "ssc.spec")

if not os.path.exists(_WINDOWS_SPEC):
    raise FileNotFoundError(f"Missing spec file: {_WINDOWS_SPEC}")

with open(_WINDOWS_SPEC, "r", encoding="utf-8") as f:
    exec(compile(f.read(), _WINDOWS_SPEC, "exec"), globals(), locals())
