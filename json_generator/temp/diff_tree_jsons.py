import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


APP_DIR = Path("app_jsons")
CANON_DIR = Path("canon_jsons")

FILES = [
    "tree.json",
    "editor_tree.json",
    "nta_tree.json",
    "tii_tree.json",
]

MAX_DIFFS_PER_FILE = 80  # bump if needed


def load(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def get_children(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "treeConfig" in tree and isinstance(tree["treeConfig"], dict):
        children = tree["treeConfig"].get("children")
        if isinstance(children, list):
            return children
    if isinstance(tree.get("children"), list):
        return tree["children"]
    raise ValueError("No children list found")


def normalise_node(n: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise a node:
      - keep id always
      - keep text if present
      - keep leaf only if explicitly false
      - keep expanded/checked only if true
      - keep glyph/iconCls if present
      - children normalised, but do NOT sort lists; we compare by id maps later
    """
    out: Dict[str, Any] = {"id": n.get("id")}

    if n.get("text"):
        out["text"] = n["text"]

    if n.get("leaf") is False:
        out["leaf"] = False

    if n.get("expanded") is True:
        out["expanded"] = True

    if n.get("checked") is True:
        out["checked"] = True

    if n.get("glyph"):
        out["glyph"] = n["glyph"]

    if n.get("iconCls"):
        out["iconCls"] = n["iconCls"]

    kids = n.get("children")
    if isinstance(kids, list):
        out["children"] = [normalise_node(k) for k in kids]

    return out


def normalise_tree(tree: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "defaults": {"general": {"leaf": True, "checked": False, "expanded": False}},
        "treeConfig": {
            "id": "root",
            "leaf": False,
            "children": [normalise_node(n) for n in get_children(tree)],
        },
    }


def _children_map(node: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    kids = node.get("children")
    if not isinstance(kids, list):
        return {}
    m: Dict[str, Dict[str, Any]] = {}
    for k in kids:
        kid_id = k.get("id")
        if kid_id is None:
            continue
        # If duplicate IDs exist, last one wins (but that itself is a bug)
        m[str(kid_id)] = k
    return m


def diff_nodes(
    canon_node: Dict[str, Any],
    app_node: Dict[str, Any],
    path: str,
    diffs: List[Tuple[str, Any, Any]],
) -> None:
    """
    Compare two normalised nodes; descend by children id maps (order independent).
    """
    # Compare scalar keys (excluding children)
    keys = set(canon_node.keys()) | set(app_node.keys())
    keys.discard("children")

    for k in sorted(keys):
        cv = canon_node.get(k, None)
        av = app_node.get(k, None)
        if cv != av:
            diffs.append((f"{path}/{k}", cv, av))

    # Compare children by id
    c_map = _children_map(canon_node)
    a_map = _children_map(app_node)

    c_ids = set(c_map.keys())
    a_ids = set(a_map.keys())

    only_c = sorted(c_ids - a_ids)
    only_a = sorted(a_ids - c_ids)

    for cid in only_c:
        diffs.append((f"{path}/children[{cid}]", "PRESENT", "MISSING"))
    for aid in only_a:
        diffs.append((f"{path}/children[{aid}]", "MISSING", "PRESENT"))

    # Recurse common children
    for cid in sorted(c_ids & a_ids):
        diff_nodes(c_map[cid], a_map[cid], f"{path}/children[{cid}]", diffs)


def diff_file(name: str) -> None:
    app_path = APP_DIR / name
    canon_path = CANON_DIR / name

    if not app_path.exists():
        print(f"[SKIP] app_jsons/{name} not found")
        return
    if not canon_path.exists():
        print(f"[SKIP] canon_jsons/{name} not found")
        return

    canon_tree = normalise_tree(load(canon_path))
    app_tree = normalise_tree(load(app_path))

    diffs: List[Tuple[str, Any, Any]] = []
    diff_nodes(canon_tree["treeConfig"], app_tree["treeConfig"], "treeConfig", diffs)

    if not diffs:
        print(f"[OK]   {name} - identical after normalisation")
        return

    print(f"[DIFF] {name} - {len(diffs)} difference(s) after normalisation")
    for i, (p, cv, av) in enumerate(diffs[:MAX_DIFFS_PER_FILE], start=1):
        print(f"  {i:02d}. {p}")
        print(f"      canon: {cv}")
        print(f"      app:   {av}")

    if len(diffs) > MAX_DIFFS_PER_FILE:
        print(f"  ... truncated, showing first {MAX_DIFFS_PER_FILE} of {len(diffs)} diffs")


def main() -> None:
    for name in FILES:
        diff_file(name)


if __name__ == "__main__":
    main()
