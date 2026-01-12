import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional


# ----------------------------
# Helpers: layer JSON -> allowed LayerKeys
# ----------------------------

def _collect_layer_keys_from_layer_json(layer_json: Dict[str, Any]) -> Set[str]:
    """
    Build the set of all LayerKeys that are resolvable from this portal's layer JSON.

    Includes:
      - Top-level layerKey for every entry in layers[]
      - For switchlayer entries: every child layerKey in layers[]
    """
    allowed: Set[str] = set()

    layers = layer_json.get("layers", [])
    if not isinstance(layers, list):
        raise ValueError("Invalid layer JSON: 'layers' is not a list")

    for layer in layers:
        if not isinstance(layer, dict):
            continue

        lk = layer.get("layerKey")
        if isinstance(lk, str) and lk.strip():
            allowed.add(lk)

        if layer.get("layerType") == "switchlayer":
            children = layer.get("layers", [])
            if not isinstance(children, list):
                raise ValueError("Invalid layer JSON: switchlayer 'layers' is not a list")
            for child in children:
                if not isinstance(child, dict):
                    continue
                clk = child.get("layerKey")
                if isinstance(clk, str) and clk.strip():
                    allowed.add(clk)

    return allowed


# ----------------------------
# Helpers: tree JSON traversal
# ----------------------------

class TreeImportError(RuntimeError):
    pass


def _is_folder_node(node: Dict[str, Any]) -> bool:
    """
    Folder detection for production trees:

    - If a node has a 'children' list, treat it as a folder
      UNLESS it explicitly declares leaf: true.
    - Production trees often omit 'leaf' for folders, so we cannot require leaf == False.
    """
    if not isinstance(node, dict):
        return False

    children = node.get("children", None)
    if isinstance(children, list):
        # Explicit leaf:true wins, even if children exists (shouldn't happen, but be defensive)
        if node.get("leaf") is True:
            return False
        return True

    # If no children list, it's not a folder
    return False


def _validate_tree_keys(
    node: Dict[str, Any],
    allowed_keys: Set[str],
    path: str = "root"
) -> None:
    """
    Fail hard if any leaf node id isn't in allowed_keys.
    """
    if not isinstance(node, dict):
        raise TreeImportError(f"Invalid tree node type at {path}")

    # Folder
    if _is_folder_node(node):
        children = node.get("children", [])
        if not isinstance(children, list):
            raise TreeImportError(f"Invalid 'children' at {path}")
        for i, child in enumerate(children):
            child_id = child.get("id", "<no-id>") if isinstance(child, dict) else "<non-dict>"
            _validate_tree_keys(child, allowed_keys, f"{path}/{i}:{child_id}")
        return

    # Leaf
    leaf_id = node.get("id")
    if not isinstance(leaf_id, str) or not leaf_id.strip():
        raise TreeImportError(f"Leaf node missing/invalid 'id' at {path}")

    if leaf_id not in allowed_keys:
        raise TreeImportError(
            f"Tree references LayerKey not in portal layer JSON: '{leaf_id}' at {path}"
        )


def _get_boolish(node: Dict[str, Any], key: str, default: Optional[int] = None) -> Optional[int]:
    if key not in node:
        return default
    val = node.get(key)
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, int):
        return 1 if val != 0 else 0
    return default



def _get_str(node: Dict[str, Any], key: str) -> Optional[str]:
    val = node.get(key)
    if isinstance(val, str):
        return val
    return None


# ----------------------------
# DB ops
# ----------------------------

def _get_portal_id(conn: sqlite3.Connection, portal_key: str) -> int:
    row = conn.execute("SELECT PortalId FROM Portals WHERE PortalKey = ?", (portal_key,)).fetchone()
    if not row:
        raise TreeImportError(f"PortalKey not found in DB: {portal_key}")
    return int(row[0])


def _delete_portal_tree(conn: sqlite3.Connection, portal_id: int) -> None:
    conn.execute("DELETE FROM PortalTreeNodes WHERE PortalId = ?", (portal_id,))


def _insert_folder(
    conn: sqlite3.Connection,
    portal_id: int,
    parent_id: Optional[int],
    display_order: int,
    folder_title: str,
    folder_id: Optional[str],
    expanded_default: Optional[int],
    checked_default: Optional[int],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO PortalTreeNodes
          (PortalId, ParentNodeId, IsFolder, FolderTitle, FolderId, ExpandedDefault, CheckedDefault, DisplayOrder)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?)
        """,
        (portal_id, parent_id, folder_title, folder_id, expanded_default, checked_default, display_order),
    )
    return int(cur.lastrowid)


def _insert_leaf(
    conn: sqlite3.Connection,
    portal_id: int,
    parent_id: Optional[int],
    display_order: int,
    layer_key: str,
    layer_title: Optional[str],
    glyph: Optional[str],
    tooltip: Optional[str],
    checked_default: Optional[int],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO PortalTreeNodes
          (PortalId, ParentNodeId, IsFolder, LayerKey, LayerTitle, Glyph, Tooltip, CheckedDefault, DisplayOrder)
        VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?)
        """,
        (portal_id, parent_id, layer_key, layer_title, glyph, tooltip, checked_default, display_order),
    )
    return int(cur.lastrowid)


def _get_service_layer_keys(conn: sqlite3.Connection) -> Set[str]:
    rows = conn.execute("SELECT LayerKey FROM ServiceLayers").fetchall()
    return {r[0] for r in rows if r and isinstance(r[0], str)}


def _collect_leaf_ids(node: Dict[str, Any], out: Set[str]) -> None:
    if not isinstance(node, dict):
        return
    if _is_folder_node(node):
        children = node.get("children", [])
        if isinstance(children, list):
            for c in children:
                _collect_leaf_ids(c, out)
        return
    leaf_id = node.get("id")
    if isinstance(leaf_id, str) and leaf_id.strip():
        out.add(leaf_id)


def _import_children(
    conn: sqlite3.Connection,
    portal_id: int,
    parent_node_id: Optional[int],
    children: List[Dict[str, Any]],
) -> None:
    for idx, child in enumerate(children):
        if not isinstance(child, dict):
            raise TreeImportError(f"Invalid child node at index {idx} (not an object)")

        if _is_folder_node(child):
            folder_title = _get_str(child, "title") or _get_str(child, "text") or "New folder"
            folder_id = _get_str(child, "id")

            expanded_default = _get_boolish(child, "expanded", default=1)  # folders usually expanded unless specified
            checked_default = _get_boolish(child, "checked", default=0)    # default false

            new_parent_id = _insert_folder(
                conn,
                portal_id=portal_id,
                parent_id=parent_node_id,
                display_order=idx,
                folder_title=folder_title,
                folder_id=folder_id,
                expanded_default=expanded_default,
                checked_default=checked_default,
            )

            subchildren = child.get("children", [])
            if not isinstance(subchildren, list):
                raise TreeImportError(f"Folder 'children' is not a list for folder id={folder_id}")
            _import_children(conn, portal_id, new_parent_id, subchildren)

        else:
            layer_key = _get_str(child, "id")
            if not layer_key:
                raise TreeImportError(f"Leaf node missing 'id' at index {idx}")

            layer_title = _get_str(child, "text") or _get_str(child, "title")

            # Store exactly as-is; exporter can decide glyph vs iconCls later
            glyph = _get_str(child, "iconCls") or _get_str(child, "glyph")

            tooltip = _get_str(child, "qtip")
            checked_default = _get_boolish(child, "checked", default=0)    # default false

            _insert_leaf(
                conn,
                portal_id=portal_id,
                parent_id=parent_node_id,
                display_order=idx,
                layer_key=layer_key,
                layer_title=layer_title,
                glyph=glyph,
                tooltip=tooltip,
                checked_default=checked_default,
            )


def import_portal_tree(
    conn: sqlite3.Connection,
    portal_key: str,
    canon_dir: Path,
    tree_filename: str,
    layer_json_filename: str,
) -> None:
    portal_id = _get_portal_id(conn, portal_key)

    tree_path = canon_dir / tree_filename
    layer_json_path = canon_dir / layer_json_filename

    if not tree_path.exists():
        raise TreeImportError(f"Missing tree file: {tree_path}")
    if not layer_json_path.exists():
        raise TreeImportError(f"Missing layer JSON file: {layer_json_path}")

    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    layer_json = json.loads(layer_json_path.read_text(encoding="utf-8"))

    allowed_keys = _collect_layer_keys_from_layer_json(layer_json)

    tree_config = tree.get("treeConfig")
    if not isinstance(tree_config, dict):
        raise TreeImportError(f"{tree_path.name}: missing/invalid treeConfig object")

    root_children = tree_config.get("children", [])
    if not isinstance(root_children, list):
        raise TreeImportError(f"{tree_path.name}: treeConfig.children is not a list")

    # Validate leaves against this portal's layer JSON set (fail hard)
    for i, child in enumerate(root_children):
        child_id = child.get("id", "<no-id>") if isinstance(child, dict) else "<non-dict>"
        _validate_tree_keys(child, allowed_keys, f"{portal_key}/root/{i}:{child_id}")

    # Also validate leaves exist in ServiceLayers (FK requirement)
    service_keys = _get_service_layer_keys(conn)

    leaf_ids: Set[str] = set()
    for child in root_children:
        _collect_leaf_ids(child, leaf_ids)

    missing_in_service = sorted(k for k in leaf_ids if k not in service_keys)
    if missing_in_service:
        raise TreeImportError(
            f"{portal_key}: tree contains {len(missing_in_service)} LayerKey(s) not present in ServiceLayers "
            f"(FK would fail). First 20: {missing_in_service[:20]}"
        )

    # Replace portal tree
    _delete_portal_tree(conn, portal_id)
    _import_children(conn, portal_id, parent_node_id=None, children=root_children)


def main() -> None:
    base = Path(__file__).resolve().parent

    db_path = base / "LayerConfig_v4.db"
    canon_dir = base / "canon_jsons"

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")
    if not canon_dir.exists():
        raise SystemExit(f"canon_jsons folder not found: {canon_dir}")

    mapping: List[Tuple[str, str, str]] = [
        # portal_key, tree_file, layer_json_file
        ("default",      "tree.json",        "default.json"),
        ("editor",       "editor_tree.json", "editor.json"),
        ("nta_default",  "nta_tree.json",    "nta_default.json"),
        ("tii_default",  "tii_tree.json",    "tii_default.json"),
    ]

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        with conn:
            for portal_key, tree_file, layer_file in mapping:
                import_portal_tree(
                    conn,
                    portal_key=portal_key,
                    canon_dir=canon_dir,
                    tree_filename=tree_file,
                    layer_json_filename=layer_file,
                )
                print(f"Imported tree for portal '{portal_key}'")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
