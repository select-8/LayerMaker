from jinja2.utils import missing
from owslib.wfs import WebFeatureService
import urllib.request
import pprint
import os
import yaml
import argparse
import logging
import sys
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import pprint
import copy

# Configure logging
logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=4)

# Constants
DEFAULT_COLUMN_VALUES = {
    "flex": 0.3,
    "inGrid": True,
    "hidden": False,
    "nulltext": None,
    "nullvalue": 0,
    "zeros": None,
    "noFilter": False
}

DEFAULT_MDATA = {
    "id": None,
    "window": None,
    "model": None,
    "isSpatial": True,
    "excel_exporter": True,
    "shp_exporter": True,
    "service": None,
    "help_page": None,
    "isSwitch": False,
    "controller": "cmv_grid",
    "sorters": []
}


@dataclass
class Config:
    url: str
    root_folder: str
    layer_name: Optional[str] = None
    overwrite: bool = True
    log_level: str = "info"


def get_feature_properties(feature_type: str, url: str) -> Dict[str, Any]:
    """Get feature properties from WFS service.

    Args:
        feature_type: Name of the feature type to retrieve
        url: URL of the WFS service

    Returns:
        Dictionary containing the feature properties

    Raises:
        ServiceException: If WFS service is unavailable
        RuntimeError: If feature type doesn't exist
    """
    try:
        cap_url = f"{url}?service=WFS&request=GetCapabilities&version=2.0.0"
        req = urllib.request.Request(cap_url)
        with urllib.request.urlopen(req, timeout=120) as response:  # increase timeout here
            xml = response.read()
        wfs = WebFeatureService(xml=xml, url=url, version="2.0.0")
        schema = wfs.get_schema(feature_type)

        if not schema or "properties" not in schema:
            raise ValueError(f"No properties found for feature type: {feature_type}")

        properties = {
            prop: {"type": schema["properties"][prop]} for prop in schema["properties"]
        }

        properties.pop('msGeometry', None)

        print('properties')
        #print(properties)
        return {"properties": properties}

    except Exception as e:
        logger.error("Failed to get properties for %s: %s", feature_type, str(e))
        raise


def determine_extype(prop_details: Dict) -> str:
    """Determine the appropriate ext type based on property details."""
    if prop_details.get("type") == "TimeInstantType":
        return "date"
    elif prop_details.get("type") in ("integer", "long", "double", "float"):
        return "number"
    return prop_details.get("type", "string")


def add_to_yaml(file: str, layer: str, url: str) -> Dict:
    new_data = []
    with open(file, encoding="utf-8") as y:
        yaml_data = yaml.load(y, Loader=yaml.FullLoader)
        yaml_columns = list(yaml_data[layer]["columns"].keys())
        wfs_properties = get_feature_properties(layer, url)
        missing_keys = {
            k: v
            for k, v in wfs_properties["properties"].items()
            if k not in yaml_columns
        }

        for k, v in missing_keys.items():
            extype = "date" if v["type"] == "TimeInstantType" else v["type"]
            new_column_values = copy.deepcopy(DEFAULT_COLUMN_VALUES)
            new_column_values.update(
                {
                    "text": k, 
                    "index": k, 
                    "renderer": extype, 
                    "extype": extype, 
                    "edit": {
                        "editable": False,
                        "groupEditIdProperty": None,
                        "groupEditDataProp": None,
                        "editServiceUrl": None,
                        "editUserRole": None
                        }
                    }
            )
            new_data.append(new_column_values)
    return new_data


def props_to_yaml(
    feature: str, properties: Dict, outfile: str
) -> Dict:
    """Convert properties to YAML format and save to file.

    Args:
        feature: Name of the feature layer
        properties: Dictionary of WFS properties
        outfile: Path to output YAML file

    Returns:
        Dictionary containing the column configurations

    Raises:
        IOError: If file cannot be written
        ValueError: If invalid properties are provided
    """
    # Validate inputs
    if not properties.get("properties"):
        raise ValueError("No properties found in input data")

    columns = {}
    column_values_dict = {}

    for prop_name, prop_details in properties["properties"].items():
        extype = determine_extype(prop_details)
        logger.debug("Processing property: %s as type: %s", prop_name, extype)

        column_values = {
            **DEFAULT_COLUMN_VALUES,
            "text": prop_name,
            "index": prop_name,
            "renderer": extype,
            "extype": extype,
            "edit": {
                "editable": False,
                "groupEditIdProperty": None,
                "groupEditDataProp": None,
                "editServiceUrl": None,
                "editUserRole": None,
            },
        }

        columns[prop_name] = column_values
        column_values_dict[prop_name] = column_values
    #print('columns')
    #pp.pprint(columns)
    config = {
        feature: {
            "mdata": {**DEFAULT_MDATA},
            "filters": [],
            "columns": columns,
        }
    }
    #print('config')
    #pp.pprint(config)
    # Ensure output directory exists
    os.makedirs(os.path.dirname(outfile), exist_ok=True)

    with open(outfile, "w") as f:
        yaml.dump(
            config,
            f,
            sort_keys=False,
            default_flow_style=False,
            indent=2,
            width=float("inf"),
            allow_unicode=True,
        )

    logger.info("Successfully generated YAML config at %s", outfile)
    print(f"Successfully generated YAML config at {outfile}")
    return column_values_dict


# def configure_sorters(num_sorters: int) -> List[Dict]:
#     """Configure sorters for the YAML output."""
#     return [{"sorter": {"field": None, "direction": None}} for _ in range(num_sorters)]


# if __name__ == "__main__":
#     # test
#     file = r"D:\DevOps\Python\yamleditor-gui\app2\grid_yamls\EditSessions.yaml"
#     layer = 'EditSessions'
#     url = "http://pms2.local/mapserver2/"

#     res = add_to_yaml(file,layer,url)
#     print(res)
