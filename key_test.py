"""Key tester: prints the Windows key code of every key you press.

Use it to check a remap, for example that Fn + right Ctrl sends the
Applications key (VK_APPS, 0x5D). It only listens; it sends nothing.

    python key_test.py            listen for 20 seconds
    python key_test.py 30         listen for 30 seconds
    python key_test.py 30 0x5D    stop with success as soon as 0x5D is pressed
"""

import ctypes
import sys
import time
from ctypes import wintypes

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
PM_REMOVE = 1
NAMES = {0x5D: "Applications", 0xA2: "Left Ctrl", 0xA3: "Right Ctrl", 0x1B: "Escape",
         0x14: "Caps Lock", 0x0D: "Enter", 0x20: "Space", 0x09: "Tab", 0x08: "Backspace",
         0xA0: "Left Shift", 0xA1: "Right Shift", 0xA4: "Left Alt", 0xA5: "Right Alt",
         0x5B: "Left Windows", 0x5C: "Right Windows", 0x2E: "Delete", 0x2D: "Insert",
         0x25: "Left Arrow", 0x26: "Up Arrow", 0x27: "Right Arrow", 0x28: "Down Arrow",
         0x24: "Home", 0x23: "End", 0x21: "Page Up", 0x22: "Page Down"}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20
    want = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM,
                                  wintypes.LPARAM)
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE,
                                         wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM,
                                      wintypes.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    found = []

    def proc(code, wparam, lparam):
        if code >= 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            name = NAMES.get(k.vkCode, chr(k.vkCode) if 0x30 <= k.vkCode <= 0x5A else "")
            print("key down: 0x%02X %s" % (k.vkCode, name), flush=True)
            if want is not None and k.vkCode == want:
                found.append(k.vkCode)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    cb = HOOKPROC(proc)
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, cb, kernel32.GetModuleHandleW(None), 0)
    if not hook:
        print("Could not start listening (Windows error %d)." % ctypes.get_last_error())
        return 2
    print("Listening for %g seconds. Press keys now." % seconds, flush=True)
    msg = wintypes.MSG()
    end = time.time() + seconds
    try:
        while time.time() < end and not found:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)
    finally:
        user32.UnhookWindowsHookEx(hook)
    if want is not None:
        if found:
            print("Success: key 0x%02X was received." % want)
            return 0
        print("Key 0x%02X was not received." % want)
        return 1
    print("Stopped listening.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
