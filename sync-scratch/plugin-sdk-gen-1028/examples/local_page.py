# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Local Page Example"
# version = "1.0.1"
# ///
import json
import orca

class LocalPage(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "Local Plugin Page"

    def get_ui(self):
        return '''<!doctype html><html><head><meta charset="utf-8"></head>
<body style="font:20px sans-serif;margin:0;padding:36px;min-height:100vh;box-sizing:border-box;background:var(--orca-bg,#f5f6fa);color:var(--orca-fg,#18212f)">
<h1>Snapmaker local plugin page</h1><p id="status">Ready to test the Python message bridge.</p>
<button id="ping" style="padding:16px;font-size:20px">Send message to Python</button>
<script>
function connect() {
  if (!window.orca) { setTimeout(connect,25); return; }
  orca.onMessage(function(data) {
    document.getElementById('status').textContent = 'Python replied: ' + data.reply;
    orca.postMessage({kind:'ack', reply:data.reply});
  });
  document.getElementById('ping').onclick = function() { orca.postMessage({kind:'ping', value:42}); };
}
connect();
</script></body></html>'''

    def on_message(self, message):
        if message.get("kind") == "ping":
            self.post_message({"reply": f"received {message['value']}"})
        elif message.get("kind") == "ack":
            self.save_config(json.dumps({"roundtrip": message.get("reply") == "received 42"}))

@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(LocalPage)
