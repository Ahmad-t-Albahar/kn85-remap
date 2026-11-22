# KN85 Remap

A small, screen-reader-friendly tool to remap keys on the Kisnt KN85 keyboard. It works with NVDA and the keyboard alone.

## Why I made this

I made this app because Kisnt's official app is not accessible with NVDA, and it requires a mouse to remap keys.

The main reason I built it is that I wanted to use the Fn key to get an Applications key, instead of pressing Shift+F10. I installed Kisnt's official app, didn't like it, and made this instead. With it, I successfully remapped Fn + right Ctrl to the Applications key.

I decided to release it because I know that others might run into the same problem I faced. In the future, it may grow into a toolkit that supports keyboards from other brands too.

## What you need

- Windows 10 or 11.
- The keyboard connected with its USB cable. The wireless receiver and Bluetooth are not supported.
- Python 3.10 or newer from python.org. During installation, tick "Add python.exe to PATH".
- wxPython, which draws the window. Install it once with this command in a Command Prompt or PowerShell window:

  pip install wxPython

You do not need the vendor driver.

## Getting the tool

On the GitHub page, use the "Code" button, then "Download ZIP", and unzip it to a folder you like. Or, if you use git, type:

  git clone https://github.com/Ahmad-t-Albahar/kn85-remap

## Starting the tool

Open a Command Prompt or PowerShell window in the kn85-remap folder and type:

  python kn85_remap.py

When the window opens, the tool checks for the keyboard. If it is not connected, you hear a message saying so.

## Using the window

Press Tab and Shift+Tab to move through these controls, in this order. The buttons also have Alt shortcuts, listed with each one.

1. Layer, a group of two radio buttons. Top layer is a key pressed on its own. Fn layer is a key pressed while holding Fn. Use the arrow keys to choose.
2. Physical key, a list of every key on the KN85. Type a letter to jump, or use the arrow keys. Fn itself is not in the list, because it must stay Fn.
3. Sends, a list of what the key should send. The first item is "Default (no change)". When you move to a key or change the layer, this list jumps to what that key sends now. So choose the layer and the key first, and Sends last.
4. Add or change remap button (Alt+A). Adds your choice to the saved list and puts you on that item, so NVDA reads it. If you chose "Default (no change)", the key's remap is removed.
5. Saved remaps list, for example "Fn layer: Right Ctrl sends Applications (context menu)". Press Delete to remove the selected remap. A message confirms what was removed.
6. Remove selected remap button (Alt+M).
7. Apply to keyboard button (Alt+P). Sends the whole saved list to the keyboard. A message tells you when it is done or if it failed. Changes are not sent until you press Apply.
8. Restore keyboard defaults button (Alt+D). Asks first. If you choose Yes, every key does its normal job again and the saved list is emptied. First, a backup of the list is saved with a name like kn85-remaps.backup-20261122-153000.json. To get it back later, rename the backup to kn85-remaps.json while the tool is closed.
9. Check connection button (Alt+C). Tells you whether the keyboard is connected.
10. Close button (Alt+E). If you have changes you have not applied, the tool asks before closing.

The status bar shows the latest result. In NVDA, press NVDA+End to read it, or NVDA+Shift+End on the laptop layout.

When the list has changes you have not applied, the window title ends with "changes not applied yet". Press NVDA+T to hear the title. The tool remembers this between runs, and when you start it, it tells you if the list has not been sent to the keyboard.

If you try to remap Escape, Tab, Enter, Space or an Alt key on the top layer, the tool asks first, because you need those keys to move around.

## Example: Fn + right Ctrl as the Applications key

1. In Layer, choose "Fn layer".
2. Tab to Physical key and type R until you hear "Right Ctrl".
3. Tab to Sends and choose "Applications (context menu)". Type A to jump near it.
4. Press Alt+A to add it.
5. Press Alt+P to apply. Wait for the "Done" message.
6. Test it: hold Fn and press right Ctrl. A context menu should open.

## The saved list, kn85-remaps.json

The keyboard cannot tell a program which keys are remapped. So the tool keeps its own record in kn85-remaps.json, in the same folder as the tool. Every time you press Apply, both layers are rewritten from this file. Keep the file, and copy it along if you move the tool.

The first time it runs, the list starts with one remap already in it: Fn layer, right Ctrl sends Applications. That is what the author's keyboard had. If you don't want it, select it in the Saved remaps list, press Delete, then press Apply.

Remaps set with the vendor app or another tool are not in this list. If you used one of those, add the same remaps here before you press Apply, or they will be overwritten. The vendor app can also overwrite this tool's remaps, so don't keep it running.

If the file is damaged and cannot be read, the tool says so, renames it to something like kn85-remaps.unreadable-20261122-153000.json so nothing is lost, and starts with an empty list.

If you share the tool with someone else, leave your kn85-remaps.json out. Their copy then starts fresh.

## Checking a key without the tool

- NVDA input help: press NVDA+1, press the key, then press NVDA+1 again to turn input help off. NVDA says the key's name.
- key_test.py: type "python key_test.py" and press keys for 20 seconds. It prints the Windows key code of each key. The Applications key is 0x5D. It hears every key typed in any program while it runs, so don't type passwords during those 20 seconds.

## Other options for advanced users

- python kn85_remap.py --check says whether the keyboard is connected.
- python kn85_remap.py --print-reports prints the exact data Apply would send, without sending it.
- python kn85_remap.py --dry-run opens the window but only prints what would be sent.
- python -m unittest discover -s tests runs the self-tests.

## Safety

- The tool sends only the same remap commands the vendor app sends. They were recorded from the vendor app (KN85 Textured Black Driver 1.0.5.0) and are checked byte for byte by the self-tests.
- It never touches firmware, lighting or macros, and it does not install a driver.
- After each layer is written, the keyboard replies with a checksum. The tool checks it and reports an error if it does not match.
- If something goes wrong, "Restore keyboard defaults" puts every key back to normal. The vendor app can do the same.
- Only "send a normal key" remaps are supported. The Applications key on the Fn layer was tested on a real KN85. Other keys use the same command format but have not all been tried. Modifier keys like Ctrl or Shift as targets are the least certain, so the Sends list marks them "untested".
- If a remap makes the keyboard hard to use, remove it and press Apply, or use Restore keyboard defaults (Alt+D, then Yes). Another keyboard plugged in at the same time also works for this.

## Known limits

- Media keys, mouse buttons, macros and lighting are not supported. The commands for them are not known.
- Only the wired USB connection (USB ID 0C45:8006) is supported.
- This is an independent tool. It is not made or supported by Kisnt.

## For developers

The reverse-engineered protocol is described in docs/PROTOCOL.md. The self-tests compare every report the tool builds with a capture of the vendor app, in tests/data.

## License

MIT. See the LICENSE file.
