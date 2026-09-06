"""Access the generated print-parameter catalog (data/params_catalog.json).

The catalog is regenerated from src/libslic3r/PrintConfig.cpp by
scripts/generate_params_catalog.py - it is derived data, never hand-edited.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import BridgeError

_CATALOG_PATH = Path(__file__).parent / "data" / "params_catalog.json"


class ParamsCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _CATALOG_PATH
        if not self.path.is_file():
            raise BridgeError(
                f"parameter catalog missing at {self.path}; run "
                "scripts/generate_params_catalog.py",
                code="catalog_missing",
            )
        with self.path.open("r", encoding="utf-8") as fh:
            self.data = json.load(fh)

    @property
    def options(self) -> dict:
        return self.data.get("options", {})

    def has_option(self, key: str) -> bool:
        return key in self.options

    def list_params(
        self,
        scope: str | None = None,
        search: str | None = None,
        limit: int = 60,
        offset: int = 0,
    ) -> dict:
        """Query the catalog by scope (machine/process/filament) and text."""
        total_all = len(self.options)
        matched: list[tuple[str, dict]] = []
        needle = (search or "").lower()
        for key, opt in self.options.items():
            if scope and scope not in opt.get("scopes", []):
                continue
            if needle:
                hay = " ".join(
                    (
                        key,
                        opt.get("label", ""),
                        opt.get("tooltip", ""),
                    )
                ).lower()
                if needle not in hay:
                    continue
            matched.append((key, opt))
        matched.sort(key=lambda kv: kv[0])
        window = matched[offset : offset + max(1, min(int(limit), 500))]
        return {
            "total_options": total_all,
            "matched": len(matched),
            "returned": len(window),
            "offset": offset,
            "options": {key: opt for key, opt in window},
            "scopes_legend": self.data.get("scopes_legend", {}),
        }
