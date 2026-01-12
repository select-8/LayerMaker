import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


CANON_MAP: List[Tuple[str, str]] = [
    ("default", "tree.json"),
    ("editor", "editor_tree.json"),
    ("nta_default", "nta_tree.json"),
    ("tii_default", "tii_tree.json"),
]


def _iter_nodes(children: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    """Depth-first yield of all nodes under the given children list."""
    stack = list(children)[::-1]
    while stack:
        node = stack.pop()
        yield node
        sub = node.get("children")
        if isinstance(sub, list) and sub:
            stack.extend(sub[::-1])


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_root_children(tree: Dict[str, Any], filename: str) -> List[Dict[str, Any]]:
    """
    Canon trees may store nodes at:
      - top-level 'children' (rare)
      - treeConfig.children (your current production format)
    """
    children = tree.get("children")
    if isinstance(children, list):
        return children

    tree_cfg = tree.get("treeConfig")
    if isinstance(tree_cfg, dict):
        children = tree_cfg.get("children")
        if isinstance(children, list):
            return children

    raise RuntimeError(f"{filename}: could not find a children list (expected treeConfig.children)")


def _get_portal_id(conn: sqlite3.Connection, portal_key: str) -> int:
    row = conn.execute(
        "SELECT PortalId FROM Portals WHERE PortalKey = ?",
        (portal_key,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"PortalKey not found in DB: {portal_key}")
    return int(row[0])


def _update_folder_expanded(
    conn: sqlite3.Connection, portal_id: int, folder_id: str, expanded: bool
) -> int:
    cur = conn.execute(
        """
        UPDATE PortalTreeNodes
        SET ExpandedDefault = ?
        WHERE PortalId = ?
          AND IsFolder = 1
          AND FolderId = ?
        """,
        (1 if expanded else 0, portal_id, folder_id),
    )
    return cur.rowcount


def _update_leaf_checked(
    conn: sqlite3.Connection, portal_id: int, layer_key: str, checked: bool
) -> int:
    cur = conn.execute(
        """
        UPDATE PortalTreeNodes
        SET CheckedDefault = ?
        WHERE PortalId = ?
          AND IsFolder = 0
          AND LayerKey = ?
        """,
        (1 if checked else 0, portal_id, layer_key),
    )
    return cur.rowcount


def main() -> None:
    here = Path(__file__).resolve().parent
    db_path = here / "LayerConfig_v4.db"
    canon_dir = here / "canon_jsons"

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")
    if not canon_dir.exists():
        raise SystemExit(f"canon_jsons folder not found: {canon_dir}")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")

        total_portals = 0
        for portal_key, canon_filename in CANON_MAP:
            canon_path = canon_dir / canon_filename
            if not canon_path.exists():
                raise SystemExit(f"Canon tree not found: {canon_path}")

            portal_id = _get_portal_id(conn, portal_key)
            tree = _load_json(canon_path)
            root_children = _get_root_children(tree, canon_filename)

            folders_updated = 0
            leaves_updated = 0
            missing_folders: List[str] = []
            missing_leaves: List[str] = []

            for node in _iter_nodes(root_children):
                node_id = (node.get("id") or "").strip()
                if not node_id:
                    continue

                sub = node.get("children")
                is_folder = isinstance(sub, list)

                if is_folder:
                    expanded = bool(node.get("expanded", False))
                    rc = _update_folder_expanded(conn, portal_id, node_id, expanded)
                    if rc == 0:
                        missing_folders.append(node_id)
                    else:
                        folders_updated += rc
                else:
                    checked = bool(node.get("checked", False))
                    rc = _update_leaf_checked(conn, portal_id, node_id, checked)
                    if rc == 0:
                        missing_leaves.append(node_id)
                    else:
                        leaves_updated += rc

            conn.commit()
            total_portals += 1

            print(f"\nPortal '{portal_key}' ({canon_filename})")
            print(f"  Folders updated: {folders_updated}")
            print(f"  Leaves updated:  {leaves_updated}")

            if missing_folders:
                uniq = sorted(set(missing_folders))
                print(f"  Missing folders in DB (first 50): {uniq[:50]}")
            if missing_leaves:
                uniq = sorted(set(missing_leaves))
                print(f"  Missing leaves in DB (first 50): {uniq[:50]}")

        print(f"\nDone. Portals processed: {total_portals}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
