import os


def parse_mapfile(map_path):
    """
    Parse a MapServer .map file with mappyfile.

    Returns (layers_by_name, error_message)
    - layers_by_name: dict name -> layer dict
    - error_message: None if ok, string if something went wrong
    """
    if not os.path.exists(map_path):
        return {}, f"File does not exist: {map_path}"

    try:
        import mappyfile
    except ImportError:
        return {}, (
            "The mappyfile library is required to parse mapfiles. "
            "Install it with: pip install mappyfile"
        )

    try:
        with open(map_path, "r", encoding="utf-8") as f:
            ms_map = mappyfile.load(f)
    except Exception as exc:
        return {}, f"Failed to parse mapfile: {exc}"

    layers = ms_map.get("layers", [])
    layers_by_name = {}
    for lyr in layers:
        name = lyr.get("name")
        if not name:
            continue
        layers_by_name[name] = lyr

    if not layers_by_name:
        return {}, "No LAYER entries found in this mapfile."

    return layers_by_name, None


def extract_styles(layer_dict):
    """
    Extract style groups from a layer.

    Returns a list of (group_name, style_title) tuples, excluding "labels".
    """
    classes = layer_dict.get("classes", []) or []
    groups = []
    seen = set()

    for cls in classes:
        group_name = cls.get("group")
        if not group_name:
            continue
        if group_name.lower() == "labels":
            continue
        if group_name in seen:
            continue
        seen.add(group_name)
        groups.append(group_name)

    # For now, style title == group name
    return [(g, g) for g in groups]


def extract_fields(layer_dict):
    """
    Best-effort extraction of fields + id property from layer METADATA.

    Returns (fields, id_prop):

    - fields: list of field names
    - id_prop: string or "" if not found

    Logic:
    - Try gml_include_items / wfs_include_items. If not "all" or "*" and not empty,
      split into individual fields.
    - Try wfs_featureid / gml_featureid as id property.
    - If no fields but id_prop exists, return [id_prop].
    """
    metadata = layer_dict.get("metadata", {}) or {}

    fields = []

    include_items = (
        metadata.get("gml_include_items")
        or metadata.get("wfs_include_items")
    )

    if include_items and isinstance(include_items, str):
        s = include_items.strip()
        if s.lower() not in ("all", "*"):
            parts = [p.strip() for p in s.split(",") if p.strip()]
            fields.extend(parts)
    elif isinstance(include_items, (list, tuple)):
        parts = [str(p).strip() for p in include_items if str(p).strip()]
        fields.extend(parts)

    # id property from common metadata keys
    id_prop = (
        (metadata.get("wfs_featureid") or "").strip()
        or (metadata.get("gml_featureid") or "").strip()
    )

    # If we have an id property but no include list, return at least that
    if not fields and id_prop:
        fields = [id_prop]

    # Deduplicate, preserve order
    seen = set()
    unique_fields = []
    for f in fields:
        if f in seen:
            continue
        seen.add(f)
        unique_fields.append(f)

    return unique_fields, id_prop
