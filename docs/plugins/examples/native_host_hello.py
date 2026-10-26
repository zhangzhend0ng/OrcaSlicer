# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Native Host Hello"
# version = "1.0.0"
# ///
"""Trusted, dependency-free S02 example; run inside the native application."""
import orca


class Hello(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Native Host Hello"

    def execute(self):
        info = orca.host.app_info()
        return orca.ExecutionResult.success(
            f"Hello from Snapmaker Orca {info['version']} ({info['mode']})",
            info["build"],
        )


@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(Hello)
