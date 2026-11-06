"""Resolve optional, separately installed Boyun browser assets."""
from importlib.resources import files

class InterfaceUnavailable(FileNotFoundError):
    """The optional interface package is not installed."""

def web_assets():
    try:
        return files('boyun_interface').joinpath('assets')
    except ModuleNotFoundError as error:
        if error.name != 'boyun_interface':
            raise
        raise InterfaceUnavailable('Install Boyun-interface to use the browser UI; CLI, MCP and HTTP APIs remain available.') from error
