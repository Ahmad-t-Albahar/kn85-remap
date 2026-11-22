"""KN85 Remap: an accessible key-remap tool for the Kisnt KN85 keyboard.

Usage:
    python kn85_remap.py              open the window
    python kn85_remap.py --dry-run    open the window, but print reports instead of sending
    python kn85_remap.py --print-reports   print what Apply would send, then exit
    python kn85_remap.py --check      say whether the keyboard is connected, then exit
"""

from __future__ import annotations

import argparse
import sys

import kn85_protocol as p
import remap_store

def run_console(args) -> int:
    if args.check:
        try:
            path = p.find_kn85()
        except p.DeviceNotFound as e:
            print(e)
            return 1
        print("Kisnt KN85 found: " + path)
        return 0
    record = remap_store.load(args.file)
    print("Remaps in record:")
    for layer, k, u in remap_store.entries(record) or []:
        print("  " + remap_store.describe(layer, k, u))
    print("Reports that Apply would send (dry run, nothing is sent):")
    p.write_all(p.DryRunTransport(), record)
    return 0


def run_gui(args) -> int:
    try:
        import wx
    except ImportError:
        print("wxPython is not installed. Install it with:  pip install wxPython")
        return 1
    import kn85_gui

    app = wx.App()
    frame = kn85_gui.MainFrame(args)
    frame.Show()
    app.MainLoop()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Accessible key remapper for the Kisnt KN85.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print reports instead of sending them to the keyboard")
    ap.add_argument("--print-reports", action="store_true",
                    help="print what Apply would send, then exit (no window)")
    ap.add_argument("--check", action="store_true",
                    help="say whether the keyboard is connected, then exit")
    ap.add_argument("--file", default=remap_store.default_path(),
                    help="remaps file (default: kn85-remaps.json next to the tool)")
    args = ap.parse_args()
    if args.check or args.print_reports:
        return run_console(args)
    return run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
