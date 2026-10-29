#!/usr/bin/env python3
"""Render the generated plugin SDK api.json into a Markdown API-reference section.

Ground truth: sync-scratch/plugin-sdk-gen-1028/api.json (live-embedded-orca export).
Property annotations are cross-read from the sibling typings/*.pyi stubs.
"""
import json
import re
import sys
from pathlib import Path

SDK = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "sync-scratch" / "plugin-sdk-gen-1028"
api = json.loads((SDK / "api.json").read_text(encoding="utf-8"))

MODULE_ORDER = [
    "orca",
    "orca.host",
    "orca.host.plate",
    "orca.host.plugin",
    "orca.host.preset",
    "orca.host.preset.bundles",
    "orca.host.ui",
    "orca.exporter",
    "orca.importer",
    "orca.script",
    "orca.slicing",
    "orca.pages",
    "orca.resource_texture",
]
MODULE_TITLE = {
    "orca": "模块 `orca` — 插件模型核心",
    "orca.host": "模块 `orca.host` — 宿主应用面（模型/几何/预设/应用信息）",
    "orca.host.plate": "模块 `orca.host.plate` — 多盘（plate）域【fork 自增，见 5.1】",
    "orca.host.plugin": "模块 `orca.host.plugin` — 插件自身信息",
    "orca.host.preset": "模块 `orca.host.preset` — 预设事务 API",
    "orca.host.preset.bundles": "模块 `orca.host.preset.bundles` — 本地预设包管理",
    "orca.host.ui": "模块 `orca.host.ui` — UI 桥（窗口/停靠面板/通知/进度）",
    "orca.exporter": "模块 `orca.exporter` — Exporter 能力（格式导出）【fork 先行，契约 provisional】",
    "orca.importer": "模块 `orca.importer` — Importer 能力（格式导入）【fork 先行，契约 provisional】",
    "orca.script": "模块 `orca.script` — Script 能力基类",
    "orca.slicing": "模块 `orca.slicing` — 切片管线能力",
    "orca.pages": "模块 `orca.pages` — Pages 能力（插件页签）",
    "orca.resource_texture": "模块 `orca.resource_texture` — 资源纹理能力",
}
SUBMODULE_NOTE = {
    "orca": "host/pages/resource_texture/script/slicing 子模块见后文各节。",
    "orca.host": "`plate` / `plugin` / `preset` / `preset.bundles` / `ui` 子模块见后文各节。",
}


# api.json 导出按字母序；Step 的声明顺序即管线顺序（Print.hpp SlicingPipelineStepPlugin），覆盖回真实顺序。
DECLARATION_ORDER = {
    "Step": ["posSlice", "posPerimeters", "posEstimateCurledExtrusions", "posPrepareInfill", "posInfill",
             "posIroning", "posContouring", "posSupportMaterial", "posDetectOverhangsForLift",
             "posSimplifyPath", "psWipeTower", "psSkirtBrim", "psGCodePostProcess"],
}


def pyi_path(module):
    parts = module.split(".")
    return SDK / "typings" / Path(*parts) / "__init__.pyi"


def property_annotations(module, cls_name):
    """Map attribute name -> annotation string for one class in a module's .pyi stub."""
    stub = pyi_path(module)
    if not stub.is_file():
        return {}
    tree = None
    import ast
    try:
        tree = ast.parse(stub.read_text(encoding="utf-8"))
    except SyntaxError:
        return {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            out = {}
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    out[item.target.id] = ast.unparse(item.annotation)
            return out
    return {}


DEFAULT_INIT_DOC = "Initialize self.  See help(type(self)) for accurate signature."


def clean_doc(name, doc):
    """Drop pybind's signature-echo head; keep the real documentation text."""
    if not doc:
        return ""
    text = doc.strip()
    if text == DEFAULT_INIT_DOC:
        return ""
    # Head form: "name(*args, **kwargs)\nOverloaded function." for overloads
    text = re.sub(rf"^{re.escape(name)}\(\*args, \*\*kwargs\)\nOverloaded function\.\n\n", "", text)
    # Signature-echo first line ("name(...) -> ret"); doc may be echo-only (no real text)
    text = re.sub(rf"^{re.escape(name)}\([^\n]*(?:\n\n|$)", "", text)
    # Numbered overload echo paragraphs ("1. name(...) -> ret\n\n")
    text = re.sub(rf"^\d+\. {re.escape(name)}\([^\n]*(?:\n\n|$)", "", text, flags=re.M)
    return text.strip()


def render_member(out, module, cls_name, member):
    name = member["name"]
    kind = member["kind"]
    doc = clean_doc(name, member.get("doc", ""))
    if kind == "property":
        ann = property_annotations(module, cls_name).get(name)
        line = f"- **`{name}`** (property"
        if ann:
            line += f": `{ann}`"
        line += ")"
        out.append(line)
        if doc:
            out.append(f"  \n  {doc}")
        return
    sigs = member.get("signatures") or []
    if kind in ("instancemethod", "builtin_function_or_method", "classmethod") and sigs:
        for sig in sigs:
            out.append(f"- **`{sig}`**")
        if doc:
            out.append(f"  \n  {doc}")
        return
    # No usable signature (e.g. staticmethod quirks) — name + doc only.
    out.append(f"- **`{name}`** ({kind})")
    if doc:
        out.append(f"  \n  {doc}")


def render_class(out, module, member):
    name = member["name"]
    out.append(f"\n#### `{name}`\n")
    members = member.get("members", [])
    for m in members:
        if m["name"] == "__init__":
            sigs = m.get("signatures") or []
            doc = clean_doc("__init__", m.get("doc", ""))
            if sigs:
                for sig in sigs:
                    out.append(f"- 构造：**`{sig}`**")
                if doc:
                    out.append(f"  \n  {doc}")
            break
    printed = False
    for m in members:
        n, k = m["name"], m["kind"]
        if n.startswith("__") and n.endswith("__"):
            continue
        render_member(out, module, name, m)
        printed = True
    if not printed and not any(m["name"] == "__init__" and (m.get("signatures") or []) for m in members):
        out.append("- （无可变更成员；枚举/标记类型）")


def render_module(module):
    members = api["modules"].get(module, [])
    out = [f"\n### {MODULE_TITLE[module]}\n"]
    if module in SUBMODULE_NOTE:
        out.append(SUBMODULE_NOTE[module] + "\n")
    classes = [m for m in members if m["kind"] == "pybind11_type"]
    # pybind 枚举类带 name/value 属性；其余类的同 kind 成员是预置实例（如 PresetEditor.filament）。
    enum_classes = {
        c["name"] for c in classes
        if {"name", "value"} <= {m["name"] for m in c.get("members", [])}
    }
    funcs = [m for m in members if m["kind"] == "builtin_function_or_method"]
    submods = [m for m in members if m["kind"] == "module"]
    enum_groups = {}
    for m in members:
        if m["kind"] not in ("pybind11_type", "builtin_function_or_method", "module"):
            enum_groups.setdefault(m["kind"], []).append(m["name"])
    for kind, names in enum_groups.items():
        if kind in DECLARATION_ORDER:
            order = {n: i for i, n in enumerate(DECLARATION_ORDER[kind])}
            names = sorted(set(names) | set(order), key=lambda n: order.get(n, 999))
        label = "枚举值" if kind in enum_classes else f"预置实例（`{kind}`）"
        if kind in ("int", "float", "str", "bool"):
            label = f"常量（{kind}）"
        out.append(f"- **{kind}** {label}：{'、'.join(f'`{n}`' for n in names)}")
    if enum_groups:
        out.append("")
    if funcs:
        out.append("**函数**\n")
        for f in funcs:
            render_member(out, module, None, f)
        out.append("")
    for c in classes:
        render_class(out, module, c)
    if submods:
        names = "、".join(f"`{m['name']}`" for m in submods)
        out.append(f"\n（子模块：{names}，见下文。）")
    return "\n".join(out)


_modules_present = [m for m in MODULE_ORDER if m in api["modules"]]
_top_level = sum(len(api["modules"][m]) for m in _modules_present)
header = [
    "<!-- 本节由脚本渲染生成：scripts/render_plugin_api_doc.py ← 插件 SDK api.json（live-embedded-orca 导出）。",
    "     API 面变化时：重建 orca_plugin_sdk_export → scripts/generate_plugin_sdk.py 重新导出 → 重跑本脚本。不要手改本节。 -->",
    "## 3. API 参考",
    "",
    f"来源：真实嵌入绑定导出（`source: {api.get('source')}`，{len(_modules_present)} 个模块、{_top_level} 个顶层成员）。签名取自 pybind11 活体导出；",
    "说明文字取自 C++ 绑定原文档。`.pyi` 存根见 SDK 生成产物（第 6 节），可给编辑器提供同等补全。",
]
parts = ["\n".join(header)]
for mod in MODULE_ORDER:
    if mod in api["modules"]:
        parts.append(render_module(mod))

Path(sys.argv[1] if len(sys.argv) > 1 else "api_reference_gen.md").write_text(
    "\n".join(parts) + "\n", encoding="utf-8")
print("rendered", len("\n".join(parts)), "chars")
