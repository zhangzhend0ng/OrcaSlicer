"""Minimal 3MF writer (OPC zip + model XML) for mesh wrapping.

The bridge only needs to hand a mesh to Orca as a 3mf; this produces a
minimal, spec-conformant archive (content types, relationships, one mesh
object). Parsing 3mf files stays with trimesh - only the tiny write path is
home-grown, per the integration plan (3MF = zipfile + XML).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from ..errors import BridgeError

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0"
   Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _model_xml(mesh, unit: str = "millimeter") -> str:
    if mesh.vertices.shape[1] != 3 or mesh.faces.shape[1] != 3:
        raise BridgeError("mesh must have 3D vertices and triangle faces",
                          code="bad_mesh_shape")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="%s" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        % _xml_escape(unit),
        " <resources>",
        '  <object id="1" type="model">',
        '   <mesh>',
        '    <vertices>',
    ]
    for v in mesh.vertices:
        parts.append(
            '     <vertex x="%.6f" y="%.6f" z="%.6f"/>' % (v[0], v[1], v[2])
        )
    parts.append("    </vertices>")
    parts.append("    <triangles>")
    for f in mesh.faces:
        parts.append(
            '     <triangle v1="%d" v2="%d" v3="%d"/>' % (f[0], f[1], f[2])
        )
    parts.append("    </triangles>")
    parts.append("   </mesh>")
    parts.append("  </object>")
    parts.append(" </resources>")
    parts.append(' <build><item objectid="1"/></build>')
    parts.append("</model>")
    return "\n".join(parts)


def write_minimal_3mf(mesh, out_path: str | Path, unit: str = "millimeter") -> Path:
    out = Path(out_path)
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
            zf.writestr("_rels/.rels", _RELS)
            zf.writestr("3D/3dmodel.model", _model_xml(mesh, unit))
    except OSError as exc:
        raise BridgeError(f"failed to write 3mf: {exc}", code="write_failed") from exc
    return out
