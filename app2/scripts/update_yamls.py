import os
import yaml

def update_yaml_file(source_path, target_path):
    with open(source_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    updated = False

    for top_key, top_val in data.items():
        if isinstance(top_val, dict) and "columns" in top_val:
            columns = top_val["columns"]
            for col_name, col_def in columns.items():
                edit = col_def.get("edit")
                if isinstance(edit, dict) and "groupEditService" in edit:
                    edit["groupEditIdProperty"] = edit.pop("groupEditService")
                    updated = True

    if updated:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, sort_keys=False)
        print(f"Updated: {target_path}")
    else:
        print(f"No changes: {target_path} (copied as-is)")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, sort_keys=False)

def process_yaml_folder(source_folder, output_folder):
    for root, _, files in os.walk(source_folder):
        for file in files:
            if file.endswith('.yaml') or file.endswith('.yml'):
                source_path = os.path.join(root, file)
                relative_path = os.path.relpath(source_path, source_folder)
                target_path = os.path.join(output_folder, relative_path)
                update_yaml_file(source_path, target_path)

# Replace these paths with your actual folder paths
source_folder = r'D:\DevOps\Python\yamleditor-gui\app2\grid_yamls'
output_folder = r'D:\DevOps\Python\yamleditor-gui\app2\grid_yamls2'

process_yaml_folder(source_folder, output_folder)
