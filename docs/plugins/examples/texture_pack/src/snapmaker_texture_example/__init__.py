"""The host provides orca; it is not a pip dependency."""
from pathlib import Path
import orca


class ExampleTextures(orca.resource_texture.ResourceTexturePluginCapabilityBase):
    def get_name(self):
        return "Snapmaker example textures"

    def get_texture_dir(self):
        # Keep resources inside the wheel package. The host resolves this once
        # when loading the capability, then owns the selected image bytes.
        return str(Path(__file__).parent / "textures")


@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(ExampleTextures)
