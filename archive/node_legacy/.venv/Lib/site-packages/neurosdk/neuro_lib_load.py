import platform
import pathlib
import sys
from ctypes import CDLL

_libname = None
if sys.platform == "win32":
    arc = platform.architecture()
    if arc[0].__contains__("64"):
        _libname = pathlib.Path(__file__).parent.resolve() / "libs" / "win" / "neurosdk2-x64.dll"
    else:
        _libname = pathlib.Path(__file__).parent.resolve() / "libs" / "win" / "neurosdk2-x32.dll"
elif sys.platform.startswith("linux"):
    _libname = "libneurosdk2.so"
elif sys.platform == "darwin":
    _libname = pathlib.Path(__file__).parent.resolve() / "libs" / "macos" / "libneurosdk2.dylib"
else:
    raise Exception("This platform (%s) is currently not supported by py_neurosdk." % sys.platform)

_neuro_lib = CDLL(str(_libname))