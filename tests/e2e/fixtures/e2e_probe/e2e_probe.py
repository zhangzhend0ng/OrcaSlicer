# /// script
# requires-python = ">=3.10"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "E2E Probe"
# description = "Committed fixture for the tests/e2e lifecycle scenarios: a Pages capability whose tab presence/absence is asserted across install, enable, disable, uninstall, restart and restore legs."
# author = "port-e2e"
# version = "1.0.0"
# ///
"""E2E probe plugin -- see tests/e2e/README.md.

Deliberately minimal: one Pages capability named "E2E Probe" serving a static page.
The host-side scenarios assert on the *lifecycle surface* (rows, tabs, sidecar, disk),
not on this page's content, so the fixture stays dependency-free and deterministic.
"""

import orca


class ProbePage(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "E2E Probe"

    def get_ui(self):
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>E2E Probe</title></head>"
            "<body style='font-family:sans-serif;padding:2em'>"
            "<h1>e2e-probe-ok</h1>"
            "<p>Static fixture page for tests/e2e lifecycle scenarios.</p>"
            "</body></html>"
        )


@orca.plugin
class E2EProbePackage(orca.base):
    def register_capabilities(self):
        orca.register_capability(ProbePage)
