"""The tool's own record of remaps, saved as JSON next to the tool.

The keyboard cannot report its current remaps, so this file is the only
memory of what has been written. Both layers are always rewritten from it.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time

import kn85_protocol as p

FILE_NAME = "kn85-remaps.json"

# What the keyboard already had when this tool was made (set once with the
# vendor app): Fn + right Ctrl sends Applications.
SEED = {p.LAYER_TOP: {}, p.LAYER_FN: {98: 0x65}}


def default_path() -> str:
    base = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False)
                                           else __file__))
    return os.path.join(base, FILE_NAME)


def empty() -> dict[str, dict[int, int]]:
    return {layer: {} for layer in p.LAYERS}


def load_state(path: str) -> tuple[dict[str, dict[int, int]], bool]:
    """Load (record, applied). A missing file gives the seed record, not applied.

    Any problem with the file's content raises ValueError."""
    if not os.path.exists(path):
        return {k: dict(v) for k, v in SEED.items()}, False
    with open(path, encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError("The file is not valid JSON: %s" % e) from None
    try:
        record = empty()
        for item in raw["remaps"]:
            layer = item["layer"]
            key_index = int(item["key_index"])
            usage = int(item["usage"])
            if layer not in p.LAYERS or key_index not in p.VALID_KEY_INDEXES                     or usage not in p.TARGET_NAME:
                raise ValueError("bad entry %r" % (item,))
            record[layer][key_index] = usage
        applied = bool(raw.get("applied", True))
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        raise ValueError("The file's content is not a valid remaps list (%s)." % e) from None
    return record, applied


def load(path: str) -> dict[str, dict[int, int]]:
    return load_state(path)[0]


def set_aside_bad_file(path: str) -> str:
    """Rename an unreadable file so it is kept but no longer used. Returns new name."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    new = os.path.splitext(path)[0] + ".unreadable-%s.json" % stamp
    os.replace(path, new)
    return new


def backup(path: str) -> str:
    """Copy the file to a time-stamped backup next to it. Returns the backup path."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.splitext(path)[0] + ".backup-%s.json" % stamp
    shutil.copyfile(path, dest)
    return dest


def save(path: str, record: dict[str, dict[int, int]], applied: bool = False) -> None:
    items = []
    for layer in p.LAYERS:
        for key_index, usage in sorted(record[layer].items()):
            items.append({
                "layer": layer,
                "key_index": key_index,
                "key_name": p.physical_key_name(key_index),
                "usage": usage,
                "usage_name": p.TARGET_NAME[usage],
            })
    data = {"version": 1, "note": "Remaps written by kn85-remap. The keyboard "
            "cannot report them, so keep this file.",
            "applied": applied, "remaps": items}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def describe(layer: str, key_index: int, usage: int) -> str:
    return "%s: %s sends %s" % (p.LAYER_LABEL[layer], p.physical_key_name(key_index),
                                p.TARGET_NAME[usage])


def entries(record) -> list[tuple[str, int, int]]:
    return [(layer, k, u) for layer in p.LAYERS for k, u in sorted(record[layer].items())]
