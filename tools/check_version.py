"""Fail CI when plugin and marketplace versions drift apart."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
manifest = json.loads((ROOT / "package.v2.json").read_text(encoding="utf-8"))["MediaRatings"]
tree = ast.parse((ROOT / "plugins.v2/mediaratings/__init__.py").read_text(encoding="utf-8"))
plugin_version = None
for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "MediaRatings":
        for item in node.body:
            if isinstance(item, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "plugin_version" for target in item.targets
            ):
                plugin_version = ast.literal_eval(item.value)

if plugin_version != manifest["version"]:
    raise SystemExit(f"plugin_version={plugin_version!r} does not match manifest={manifest['version']!r}")
if f"v{plugin_version}" not in manifest.get("history", {}):
    raise SystemExit(f"history has no entry for v{plugin_version}")
print(f"MediaRatings version contract: {plugin_version}")
