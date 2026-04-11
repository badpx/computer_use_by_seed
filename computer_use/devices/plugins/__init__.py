"""Built-in device plugins."""

import importlib


def __getattr__(name):
    qualified_name = f'{__name__}.{name}'
    try:
        module = importlib.import_module(f'.{name}', __name__)
    except ModuleNotFoundError as exc:
        if exc.name == qualified_name:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
        raise
    globals()[name] = module
    return module


__all__ = ['android_adb', 'local', 'vnc']
