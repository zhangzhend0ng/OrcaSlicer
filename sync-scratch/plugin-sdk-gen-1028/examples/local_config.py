# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Local Config Contract"
# version = "1.0.0"
# ///
import orca


class ConfigContract(orca.script.ScriptPluginCapabilityBase):
    def get_name(self): return "Config Contract"
    def get_default_config(self): return {"value": 1}
    def has_config_ui(self): return True
    def get_config_ui(self):
        return '''<h1>Custom configuration</h1><p id="value">Loading</p>
<button onclick="orca.saveConfig({value:42})">Save value 42</button>
<button onclick="orca.restoreDefaults()">Restore value 1</button>
<script>
orca.onConfig(config => document.getElementById('value').textContent = 'Saved value: ' + config.value);
if (orca.getContext().scope !== 'global') throw new Error('Incorrect scope');
</script>'''
    def execute(self): return orca.ExecutionResult.success("Use Config to edit this capability")


@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(ConfigContract)
