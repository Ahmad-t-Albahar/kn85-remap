"""The accessible window of KN85 Remap (wxPython)."""

from __future__ import annotations

import os
import threading

import wx

import kn85_protocol as p
import remap_store

APP_NAME = "KN85 Remap"
DEFAULT_LABEL = "Default (no change)"

# Top-layer keys people need to move around Windows and this tool.
RISKY_TOP_KEYS = {1, 37, 85, 94, 93, 95}  # Esc, Tab, Enter, Space, Left Alt, Right Alt
UNTESTED_TARGETS = set(range(0xE0, 0xE8))  # modifier keys as targets


def target_label(usage: int, name: str) -> str:
    return name + " (untested)" if usage in UNTESTED_TARGETS else name


class MainFrame(wx.Frame):
    def __init__(self, args):
        super().__init__(None, title=APP_NAME, size=(560, 720))
        self.dry_run = args.dry_run
        self.path = args.file
        self.busy = False
        self.pending = False
        self.startup_note = ""
        try:
            self.record, applied = remap_store.load_state(self.path)
            self.pending = not applied
            if not os.path.exists(self.path):
                remap_store.save(self.path, self.record, applied=applied)
        except ValueError as e:
            self.record = remap_store.empty()
            self.pending = True
            try:
                kept = remap_store.set_aside_bad_file(self.path)
                where = "It was renamed to %s so nothing in it is lost." % kept
            except OSError:
                where = "It could not be renamed, so the tool will save to a new file " \
                        "instead: %s.new" % self.path
                self.path = self.path + ".new"
            self.startup_note = ("The saved remaps file could not be read:\n%s\n\n%s\n\n"
                                 "The tool starts with an empty list. Add your remaps "
                                 "again before you press Apply." % (e, where))
        except OSError as e:
            self.record = remap_store.empty()
            self.pending = True
            self.path = self.path + ".new"
            self.startup_note = ("The saved remaps file could not be opened (%s). The tool "
                                 "starts with an empty list and saves to %s." % (e, self.path))

        self.keys = p.remappable_keys()
        self.targets = [(None, DEFAULT_LABEL)] + list(p.TARGETS)

        panel = wx.Panel(self)
        s = wx.BoxSizer(wx.VERTICAL)

        # Creation order is tab order and also gives each control its label.
        self.layer = wx.RadioBox(
            panel, label="&Layer",
            choices=["Top layer (key pressed on its own)",
                     "Fn layer (key pressed while holding Fn)"],
            majorDimension=1, style=wx.RA_SPECIFY_COLS)
        s.Add(self.layer, 0, wx.EXPAND | wx.ALL, 8)

        s.Add(wx.StaticText(panel, label="Physical &key:"), 0, wx.LEFT | wx.TOP, 8)
        self.key_list = wx.ListBox(panel, choices=[n for _, n in self.keys],
                                   style=wx.LB_SINGLE)
        s.Add(self.key_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        s.Add(wx.StaticText(panel, label="&Sends:"), 0, wx.LEFT | wx.TOP, 8)
        self.target_list = wx.ListBox(
            panel, choices=[DEFAULT_LABEL] + [target_label(u, n) for u, n in p.TARGETS],
            style=wx.LB_SINGLE)
        s.Add(self.target_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.add_btn = wx.Button(panel, label="&Add or change remap")
        s.Add(self.add_btn, 0, wx.ALL, 8)

        s.Add(wx.StaticText(panel, label="Saved &remaps:"), 0, wx.LEFT | wx.TOP, 8)
        self.remap_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        s.Add(self.remap_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.remove_btn = wx.Button(panel, label="Re&move selected remap")
        self.apply_btn = wx.Button(panel, label="A&pply to keyboard")
        row.Add(self.remove_btn, 0, wx.RIGHT, 8)
        row.Add(self.apply_btn, 0)
        s.Add(row, 0, wx.ALL, 8)

        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.defaults_btn = wx.Button(panel, label="Restore keyboard &defaults...")
        self.check_btn = wx.Button(panel, label="Check &connection")
        self.close_btn = wx.Button(panel, label="Clos&e")
        row2.Add(self.defaults_btn, 0, wx.RIGHT, 8)
        row2.Add(self.check_btn, 0, wx.RIGHT, 8)
        row2.Add(self.close_btn, 0)
        s.Add(row2, 0, wx.ALL, 8)

        panel.SetSizer(s)
        self.CreateStatusBar()

        self.layer.Bind(wx.EVT_RADIOBOX, self.on_selection_changed)
        self.key_list.Bind(wx.EVT_LISTBOX, self.on_selection_changed)
        self.add_btn.Bind(wx.EVT_BUTTON, self.on_add)
        self.remove_btn.Bind(wx.EVT_BUTTON, self.on_remove)
        self.remap_list.Bind(wx.EVT_KEY_DOWN, self.on_remap_key)
        self.apply_btn.Bind(wx.EVT_BUTTON, self.on_apply)
        self.defaults_btn.Bind(wx.EVT_BUTTON, self.on_defaults)
        self.check_btn.Bind(wx.EVT_BUTTON, self.on_check)
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.key_list.SetSelection(0)
        self.refresh_remaps()
        self.on_selection_changed(None)
        self.update_title()
        self.layer.SetFocus()
        wx.CallAfter(self.startup_check)

    # --- helpers -------------------------------------------------------

    def current_layer(self) -> str:
        return p.LAYERS[self.layer.GetSelection()]

    def current_key(self):
        i = self.key_list.GetSelection()
        return self.keys[i][0] if i != wx.NOT_FOUND else None

    def status(self, text: str) -> None:
        self.SetStatusText(text)

    def tell(self, text: str, icon=wx.ICON_INFORMATION) -> None:
        self.status(text.split("\n")[0])
        wx.MessageBox(text, APP_NAME, wx.OK | icon, self)

    def refresh_remaps(self, select=None) -> None:
        self.entries = remap_store.entries(self.record)
        self.remap_list.Set([remap_store.describe(*e) for e in self.entries])
        if self.entries:
            idx = 0
            if select is not None:
                for i, e in enumerate(self.entries):
                    if e[:2] == select:
                        idx = i
            self.remap_list.SetSelection(min(idx, len(self.entries) - 1))

    def save_record(self, pending: bool) -> bool:
        """Save the list and the applied flag. Returns False (after telling the
        user) if the file could not be written."""
        try:
            remap_store.save(self.path, self.record, applied=not pending)
        except OSError as e:
            self.tell("Could not save the remaps file:\n%s\n\n%s\n\nNothing was changed."
                      % (self.path, e), wx.ICON_ERROR)
            return False
        self.pending = pending
        self.update_title()
        return True

    def mark_pending(self) -> None:
        """After a failed write the keyboard may not match the list."""
        try:
            remap_store.save(self.path, self.record, applied=False)
        except OSError:
            pass
        self.pending = True
        self.update_title()

    def update_title(self) -> None:
        base = APP_NAME + (" (dry run, nothing is sent)" if self.dry_run else "")
        self.SetTitle(base + (" - changes not applied yet" if self.pending else ""))

    def find_keyboard(self):
        """Return an error message, or None if the keyboard is connected."""
        try:
            p.find_kn85()
            return None
        except p.DeviceNotFound as e:
            return str(e)
        except OSError as e:
            return "Could not look for the keyboard: %s" % e

    # --- events --------------------------------------------------------

    def startup_check(self) -> None:
        if self.startup_note:
            self.tell(self.startup_note, wx.ICON_ERROR)
        if self.dry_run:
            self.status("Dry run: reports are printed, nothing is sent to the keyboard.")
            return
        err = self.find_keyboard()
        if err:
            self.tell(err, wx.ICON_WARNING)
        elif self.pending and self.entries and not self.startup_note:
            self.tell("Kisnt KN85 keyboard connected.\n\nThe saved remaps list has not "
                      "been sent to this keyboard yet. Check the Saved remaps list, then "
                      "press Apply to keyboard (Alt+P) to send it.")
        else:
            self.status("Kisnt KN85 keyboard connected.")

    def on_check(self, event) -> None:
        err = self.find_keyboard()
        if err:
            self.tell(err, wx.ICON_WARNING)
        else:
            self.tell("The Kisnt KN85 keyboard is connected.")

    def on_selection_changed(self, event) -> None:
        """Show what the chosen key currently sends on the chosen layer."""
        key = self.current_key()
        usage = self.record[self.current_layer()].get(key)
        idx = 0
        if usage is not None:
            idx = [u for u, _ in self.targets].index(usage)
        self.target_list.SetSelection(idx)

    def on_add(self, event) -> None:
        key = self.current_key()
        t = self.target_list.GetSelection()
        if key is None or t == wx.NOT_FOUND:
            self.tell("Choose a physical key and what it sends first.")
            return
        layer = self.current_layer()
        usage = self.targets[t][0]
        name = p.physical_key_name(key)
        old = self.record[layer].get(key)
        if usage == old:
            what = "has no remap" if usage is None else \
                "already sends %s" % p.TARGET_NAME[usage]
            self.tell("%s on the %s %s. Nothing changed." % (name, p.LAYER_LABEL[layer], what))
            return
        if usage is not None and layer == p.LAYER_TOP and key in RISKY_TOP_KEYS:
            answer = wx.MessageBox(
                "%s on the top layer is used to move around Windows and this tool. If "
                "you change it, it stops doing its normal job until you remove the remap "
                "or restore keyboard defaults.\n\nChange it anyway?" % name,
                APP_NAME, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
            if answer != wx.YES:
                self.status("Nothing changed.")
                return
        if usage is None:
            del self.record[layer][key]
            msg = "Removed: %s on the %s. Press Apply to send it." % (name, p.LAYER_LABEL[layer])
        else:
            self.record[layer][key] = usage
            msg = "Added: %s. Press Apply to send it." % remap_store.describe(layer, key, usage)
        if not self.save_record(pending=True):
            if old is None:
                self.record[layer].pop(key, None)
            else:
                self.record[layer][key] = old
            return
        had_focus = wx.Window.FindFocus() is self.remap_list
        self.refresh_remaps(select=(layer, key))
        if usage is None or had_focus:
            self.tell(msg)
        else:
            # Moving to the new item makes NVDA read it.
            self.status(msg)
            self.remap_list.SetFocus()

    def on_remap_key(self, event) -> None:
        if event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
            self.on_remove(None)
        else:
            event.Skip()

    def on_remove(self, event) -> None:
        i = self.remap_list.GetSelection()
        if not self.entries:
            self.tell("There is no remap to remove.")
            return
        if i == wx.NOT_FOUND:
            self.tell("Select a remap in the Saved remaps list first.")
            return
        layer, key, usage = self.entries[i]
        del self.record[layer][key]
        if not self.save_record(pending=True):
            self.record[layer][key] = usage
            return
        self.refresh_remaps()
        if self.entries:
            self.remap_list.SetSelection(min(i, len(self.entries) - 1))
        self.on_selection_changed(None)
        msg = "Removed: %s. Press Apply to send it." % remap_store.describe(layer, key, usage)
        if not self.entries:
            msg += " The list is now empty."
        self.tell(msg)

    def start_write(self, record, on_done) -> None:
        if self.busy:
            self.status("Still writing to the keyboard, please wait.")
            return
        self.busy = True
        self.status("Writing to the keyboard...")
        wx.BeginBusyCursor()

        def work():
            err = None
            t = None
            try:
                t = p.open_transport(self.dry_run)
                p.write_all(t, record)
            except (p.DeviceNotFound, p.ProtocolError) as e:
                err = str(e)
            except Exception as e:  # never leave the window stuck in "busy"
                err = "Unexpected error: %s: %s" % (type(e).__name__, e)
            finally:
                if t is not None:
                    try:
                        t.close()
                    except Exception:
                        pass
                wx.CallAfter(finish, err)

        def finish(err):
            if not self:
                return
            self.busy = False
            if wx.IsBusy():
                wx.EndBusyCursor()
            on_done(err)

        threading.Thread(target=work, daemon=True).start()

    def on_apply(self, event) -> None:
        record = {k: dict(v) for k, v in self.record.items()}

        def done(err):
            if err:
                self.mark_pending()
                self.tell("Apply failed. The keyboard may be partly updated. Press Apply "
                          "again when it is connected.\n\n" + err, wx.ICON_ERROR)
                return
            if record != self.record:  # list changed while writing
                self.mark_pending()
            else:
                self.save_record(pending=False)
            lines = [remap_store.describe(*e) for e in remap_store.entries(record)]
            n = len(lines)
            head = ("Dry run finished. Nothing was sent; the reports were printed "
                    "to the console." if self.dry_run else
                    "Done. Both layers were written to the keyboard.")
            body = ("%d remap%s active:\n" % (n, "" if n == 1 else "s") + "\n".join(lines)) \
                if n else "No remaps: every key does its normal job."
            self.tell(head + "\n\n" + body)
        self.start_write(record, done)

    def on_defaults(self, event) -> None:
        if self.busy:
            self.status("Still writing to the keyboard, please wait.")
            return
        n = len(self.entries)
        answer = wx.MessageBox(
            "Restore keyboard defaults?\n\nThis writes both layers with no remaps, so "
            "every key goes back to its normal job. Your %d saved remap%s will be "
            "removed from the list. A backup copy of the list is kept first.\n\n"
            "Choose Yes to restore defaults, or No to cancel." % (n, "" if n == 1 else "s"),
            APP_NAME, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
        if answer != wx.YES:
            self.status("Restore defaults cancelled. Nothing changed.")
            return
        backup = None
        if self.entries:
            try:
                remap_store.save(self.path, self.record, applied=not self.pending)
                backup = remap_store.backup(self.path)
            except OSError as e:
                self.tell("Could not make a backup of your saved remaps, so nothing was "
                          "changed.\n\n%s" % e, wx.ICON_ERROR)
                return

        def done(err):
            if err:
                self.mark_pending()
                self.tell("Restore defaults failed. The keyboard may be partly reset. Your "
                          "saved list was not changed; press Apply to put your remaps "
                          "back.\n\n" + err, wx.ICON_ERROR)
                return
            self.record = remap_store.empty()
            self.save_record(pending=False)
            self.refresh_remaps()
            self.on_selection_changed(None)
            msg = ("Dry run finished. Nothing was sent." if self.dry_run else
                   "Keyboard defaults restored. No keys are remapped now.")
            if backup:
                msg += "\n\nYour old list was saved as %s." % os.path.basename(backup)
            self.tell(msg)
            self.defaults_btn.SetFocus()
        self.start_write(remap_store.empty(), done)

    def on_close(self, event) -> None:
        if self.busy and event.CanVeto():
            self.tell("Please wait, the tool is still writing to the keyboard.")
            event.Veto()
            return
        if self.pending and event.CanVeto():
            answer = wx.MessageBox(
                "Your saved remaps have not been sent to the keyboard yet. Close anyway? "
                "They stay in the list and are sent the next time you press Apply.",
                APP_NAME, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if answer != wx.YES:
                event.Veto()
                return
        self.Destroy()
