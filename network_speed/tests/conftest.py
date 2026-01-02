import sys


_ORIG_UNRAISABLE = sys.unraisablehook


def _silence_bad_fd(unraisable):
    exc = unraisable.exc_value
    obj_repr = repr(unraisable.object)
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 9:
        if "_Py3Utf8Output" in obj_repr:
            return
    _ORIG_UNRAISABLE(unraisable)


def pytest_configure():
    sys.unraisablehook = _silence_bad_fd
