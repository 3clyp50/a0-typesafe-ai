from importlib.metadata import version

import pydantic

from helpers import process
from helpers.extension import Extension
from helpers.plugins import call_plugin_hook


class TypeSafeDependencies(Extension):
    def execute(self, **kwargs):
        if call_plugin_hook("typesafe_ai", "ensure_dependencies", raise_on_error=False):
            if pydantic.__version__ != version("pydantic"):
                process.restart_process()
