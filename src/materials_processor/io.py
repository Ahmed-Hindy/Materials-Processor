import json
import os
from pathlib import Path
from typing import Any, Dict


def load_node_tree_json(path):
    """
    Load a node-tree JSON file and return its top-level object.
    
    Parameters:
        path (str | pathlib.Path): Path to the JSON file. User-home references are expanded.
    
    Returns:
        dict: The decoded JSON object.
    
    Raises:
        FileNotFoundError: If the path does not reference a file.
        ValueError: If the decoded JSON value is not a dictionary.
    """
    path = Path(path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")

    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object (dict) at top level, found {type(data).__name__}")

    return data


def _convert_to_serializable(obj):
    """
    Convert an object to a JSON-serializable fallback value for debugging.
    
    Parameters:
    	obj: Object requiring conversion.
    
    Returns:
    	str: The object's path, name, string representation, or a fallback marker.
    """
    import hou

    if not obj:
        return "None"
    elif isinstance(obj, hou.VopNode):
        return obj.path()
    elif isinstance(obj, tuple):
        return "tuple"
    elif isinstance(obj, hou.Parm):
        return obj.name()
    try:
        return str(obj)
    except:
        return "None2"  # Handle cases where conversion fails


def dump_dict_to_json(data: Dict[str, Any], path: str):
    """
    Write dictionary data as indented JSON to the specified file, creating its parent directory when needed.
    
    Parameters:
        data (Dict[str, Any]): The dictionary to serialize.
        path (str): The output file path.
    
    Returns:
        bool: True after the JSON file is written.
    """
    folder = os.path.dirname(path)
    file_name_with_ext = os.path.basename(path)
    file_name, file_ext = os.path.splitext(file_name_with_ext)
    if not os.path.exists(folder):
        os.makedirs(folder)

    json_str = json.dumps(data, default=_convert_to_serializable, indent=4)

    # with open(f"{folder}/example_material_tree.json", "w") as json_file:
    with open(f"{folder}/{file_name}{file_ext}", "w") as json_file:
        json_file.write(json_str)

    return True
