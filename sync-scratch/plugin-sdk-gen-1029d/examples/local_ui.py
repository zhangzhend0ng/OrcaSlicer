# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Local UI Example"
# version = "1.0.0"
# ///
import json
import orca


def page(title, automatic=False):
    return '''<!doctype html><html><head><meta charset="utf-8"></head>
<body style="padding:24px"><h1>''' + title + '''</h1><p id="status">Ready</p>
<button id="ping">Test Python UI bridge</button><script>
function connect(){
 document.getElementById('status').textContent = 'Bridge ' + typeof window.orca + ' / ' + typeof window.wx;
 if(!window.orca || !window.wx){setTimeout(connect,25);return;}
 orca.onMessage(function(data){document.getElementById('status').textContent=data.reply;orca.postMessage({kind:'ack',reply:data.reply});});
 document.getElementById('ping').onclick=function(){orca.postMessage({kind:'ping'});};
 ''' + ("document.getElementById('ping').click();" if automatic else "") + '''
}
connect();</script></body></html>'''


class LocalUi(orca.script.ScriptPluginCapabilityBase):
    def get_name(self): return "Local UI"

    def mark(self, key):
        config = json.loads(self.get_config())
        config[key] = True
        if not self.save_config(json.dumps(config)):
            raise RuntimeError("Cannot save UI test result")

    def window_message(self, data):
        if data.get("kind") == "ping":
            assert orca.host.plugin.storage()
            with orca.host.ui.ProgressDialog("Plugin progress", "Testing progress", maximum=10, style=0) as progress:
                assert progress.is_open()
                assert progress.update(5, "Halfway")
                progress.start_pulse(50)
                progress.stop_pulse()
            self.window.post({"reply": "Window and progress passed"})
        elif data.get("kind") == "ack":
            self.mark("window_roundtrip")

    def dock_message(self, data):
        if data.get("kind") == "ping":
            self.panel.hide()
            self.panel.show()
            self.panel.post({"reply": "Dock passed"})
        elif data.get("kind") == "ack":
            self.mark("dock_roundtrip")

    def execute(self):
        self.save_config("{}")
        self.window = orca.host.ui.create_window(page("Snapmaker plugin window"), title="Plugin UI contract", on_message=self.window_message)
        self.panel = orca.host.ui.create_dock_panel(page("Plugin dock", True), title="Plugin dock", on_message=self.dock_message)
        orca.host.ui.push_notification(orca.host.ui.RegularNotificationLevel, "Local UI contract started")
        return orca.ExecutionResult.success("UI opened")


@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(LocalUi)
