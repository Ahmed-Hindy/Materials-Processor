import os
import json
from pathlib import Path
from typing import Any, Dict


def load_node_tree_json(path):
    """
    Load a node-tree description dumped to JSON and return it as a dictionary.

    Parameters
    ----------
    path : str | pathlib.Path
        Absolute or relative path to the *.json* file that was produced by
        `json.dump(node_tree, fp)` or a similar call.

    Returns
    -------
    dict
        The exact same structure that originally went into `json.dump`.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    json.JSONDecodeError
        If the file content is not valid JSON.
    ValueError
        If the decoded file is not a dictionary (defensive check).
    """
    path = Path(path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")

    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object (dict) at top level, found {type(data).__name__}"
        )

    return data


def _convert_to_serializable(obj):
    """
    [TEMP FOR DEBUG ONLY] Convert non-serializable objects to a string for JSON dumping.
    """
    import hou
    if not obj:
        return 'None'
    elif isinstance(obj, hou.VopNode):
        return obj.path()
    elif isinstance(obj, tuple):
        return 'tuple'
    elif isinstance(obj, hou.Parm):
        return obj.name()
    try:
        return str(obj)
    except:
        return "None2"  # Handle cases where conversion fails

def dump_dict_to_json(data: Dict[str, Any], path: str):
    """
    Dump a dictionary to a JSON file.
    """
    folder = os.path.dirname(path)
    file_name = os.path.basename(path)
    file_ext = os.path.splitext(file_name)[1]
    if not os.path.exists(folder):
        os.makedirs(folder)

    json_str = json.dumps(data, default=_convert_to_serializable, indent=4)

    # with open(f"{folder}/example_material_tree.json", "w") as json_file:
    with open(f"{folder}/{file_name}{file_ext}", "w") as json_file:
        json_file.write(json_str)

    return True
