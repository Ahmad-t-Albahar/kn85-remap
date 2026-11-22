"""Kisnt KN85 key-remap protocol, plus HID access through ctypes.

Everything here mirrors what the vendor driver (KN85 Textured Black Driver
1.0.5.0) sends, as captured with Frida. See README.md and PROTOCOL.md.

Only the Python standard library is used.
"""

from __future__ import annotations

import ctypes
import io
import sys
import time
from ctypes import wintypes

VENDOR_ID = 0x0C45
PRODUCT_ID = 0x8006
INTERFACE = "mi_02"
USAGE_PAGE = 0xFF13
REPORT_LEN = 65  # report ID 0 + 64 bytes

LAYER_TOP = "top"
LAYER_FN = "fn"
LAYERS = (LAYER_TOP, LAYER_FN)
LAYER_COMMAND = {LAYER_TOP: 0x11, LAYER_FN: 0x27}
LAYER_LABEL = {LAYER_TOP: "Top layer", LAYER_FN: "Fn layer"}

DELAY = 0.037          # seconds between reports, as the vendor app
DELAY_BEFORE_FINISH = 0.075

FN_KEY_INDEX = 96

# ---------------------------------------------------------------------------
# HID keyboard usages that a key can be told to send.  (usage, name)
# ---------------------------------------------------------------------------

_LETTERS = [(0x04 + i, chr(ord("A") + i)) for i in range(26)]
_DIGITS = [(0x1E + i, str((i + 1) % 10)) for i in range(10)]
_FKEYS = [(0x3A + i, "F%d" % (i + 1)) for i in range(12)]

TARGETS: list[tuple[int, str]] = (
    _LETTERS
    + _DIGITS
    + [
        (0x28, "Enter"),
        (0x29, "Escape"),
        (0x2A, "Backspace"),
        (0x2B, "Tab"),
        (0x2C, "Space"),
        (0x2D, "Minus and underscore"),
        (0x2E, "Equals and plus"),
        (0x2F, "Left bracket"),
        (0x30, "Right bracket"),
        (0x31, "Backslash"),
        (0x32, "Non-US hash"),
        (0x33, "Semicolon"),
        (0x34, "Apostrophe"),
        (0x35, "Grave accent"),
        (0x36, "Comma"),
        (0x37, "Period"),
        (0x38, "Slash"),
        (0x39, "Caps Lock"),
    ]
    + _FKEYS
    + [
        (0x46, "Print Screen"),
        (0x47, "Scroll Lock"),
        (0x48, "Pause"),
        (0x49, "Insert"),
        (0x4A, "Home"),
        (0x4B, "Page Up"),
        (0x4C, "Delete"),
        (0x4D, "End"),
        (0x4E, "Page Down"),
        (0x4F, "Right Arrow"),
        (0x50, "Left Arrow"),
        (0x51, "Down Arrow"),
        (0x52, "Up Arrow"),
        (0x53, "Num Lock"),
        (0x54, "Numpad Slash"),
        (0x55, "Numpad Star"),
        (0x56, "Numpad Minus"),
        (0x57, "Numpad Plus"),
        (0x58, "Numpad Enter"),
    ]
    + [(0x59 + i, "Numpad %d" % ((i + 1) % 10)) for i in range(10)]
    + [
        (0x63, "Numpad Period"),
        (0x64, "Non-US backslash"),
        (0x65, "Applications (context menu)"),
        (0xE0, "Left Ctrl"),
        (0xE1, "Left Shift"),
        (0xE2, "Left Alt"),
        (0xE3, "Left Windows"),
        (0xE4, "Right Ctrl"),
        (0xE5, "Right Shift"),
        (0xE6, "Right Alt"),
        (0xE7, "Right Windows"),
    ]
)
TARGET_NAME = dict(TARGETS)

# ---------------------------------------------------------------------------
# Physical keys of the KN85: (key_index, default HID usage), in layout order.
# Taken from black-extracted/app/layouts/rgb-keyboard.xml.
# ---------------------------------------------------------------------------

PHYSICAL_KEYS: list[tuple[int, int]] = [
    (1, 0x29), (2, 0x3A), (3, 0x3B), (4, 0x3C), (5, 0x3D), (6, 0x3E), (7, 0x3F),
    (8, 0x40), (9, 0x41), (10, 0x42), (11, 0x43), (12, 0x44), (13, 0x45),
    (112, 0x46), (115, 0x48),
    (19, 0x35), (20, 0x1E), (21, 0x1F), (22, 0x20), (23, 0x21), (24, 0x22),
    (25, 0x23), (26, 0x24), (27, 0x25), (28, 0x26), (29, 0x27), (30, 0x2D),
    (31, 0x2E), (103, 0x2A), (116, 0x49), (117, 0x4A),
    (37, 0x2B), (38, 0x14), (39, 0x1A), (40, 0x08), (41, 0x15), (42, 0x17),
    (43, 0x1C), (44, 0x18), (45, 0x0C), (46, 0x12), (47, 0x13), (48, 0x2F),
    (49, 0x30), (67, 0x31), (119, 0x4C), (120, 0x4D),
    (55, 0x39), (56, 0x04), (57, 0x16), (58, 0x07), (59, 0x09), (60, 0x0A),
    (61, 0x0B), (62, 0x0D), (63, 0x0E), (64, 0x0F), (65, 0x33), (66, 0x34),
    (85, 0x28), (118, 0x4B), (121, 0x4E),
    (73, 0xE1), (74, 0x1D), (75, 0x1B), (76, 0x06), (77, 0x19), (78, 0x05),
    (79, 0x11), (80, 0x10), (81, 0x36), (82, 0x37), (83, 0x38), (84, 0xE5),
    (101, 0x52),
    (91, 0xE0), (92, 0xE3), (93, 0xE2), (94, 0x2C), (95, 0xE6), (96, 0xAF),
    (98, 0xE4), (99, 0x50), (100, 0x51), (102, 0x4F),
]


def physical_key_name(key_index: int) -> str:
    if key_index == FN_KEY_INDEX:
        return "Fn"
    for idx, code in PHYSICAL_KEYS:
        if idx == key_index:
            return TARGET_NAME.get(code, "Key %d" % key_index)
    return "Key %d" % key_index


def remappable_keys() -> list[tuple[int, str]]:
    """Physical keys the user may remap: every key except Fn itself."""
    return [(i, physical_key_name(i)) for i, _ in PHYSICAL_KEYS if i != FN_KEY_INDEX]


VALID_KEY_INDEXES = {i for i, _ in PHYSICAL_KEYS if i != FN_KEY_INDEX}

# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def _report(*payload: int) -> bytes:
    data = bytes([0]) + bytes(payload)
    return data + bytes(REPORT_LEN - len(data))


def entry_for_usage(usage: int) -> bytes:
    """4-byte key entry: 02 00 <usage> 00 sends a keyboard usage."""
    if usage not in TARGET_NAME:
        raise ValueError("unsupported usage 0x%02x" % usage)
    return bytes([0x02, 0x00, usage, 0x00])


def layer_data(remaps: dict[int, int]) -> bytes:
    """512 bytes: 128 keys x 4 bytes indexed by key_index. Zero = default."""
    buf = bytearray(512)
    for key_index, usage in remaps.items():
        if key_index not in VALID_KEY_INDEXES:
            raise ValueError("invalid key_index %r" % key_index)
        buf[key_index * 4:key_index * 4 + 4] = entry_for_usage(usage)
    return bytes(buf)


def data_reports(remaps: dict[int, int]) -> list[bytes]:
    """The 9 data reports: 8 x 64 bytes of key entries, then aa 55 trailer."""
    data = layer_data(remaps)
    reports = [b"\x00" + data[i * 64:(i + 1) * 64] for i in range(8)]
    trailer = bytearray(REPORT_LEN)
    trailer[63] = 0xAA
    trailer[64] = 0x55
    reports.append(bytes(trailer))
    return reports


def expected_checksum(remaps: dict[int, int]) -> int:
    """16-bit sum of all data bytes (incl. aa 55); the keyboard echoes it in
    the 04 02 ack (bytes 5-6, little endian). 0x00ff for an empty layer,
    0x0166 with Fn + right Ctrl = Applications, matching the vendor trace."""
    return sum(b for r in data_reports(remaps) for b in r) & 0xFFFF


CMD_BEGIN = _report(0x04, 0x18)
CMD_FINISH = _report(0x04, 0x02)
CMD_SAVE = _report(0x04, 0xF0)


def cmd_layer(layer: str) -> bytes:
    return _report(0x04, LAYER_COMMAND[layer], 0, 0, 0, 0, 0, 0, 0x09)


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------


class ProtocolError(Exception):
    pass


class DeviceNotFound(Exception):
    pass


def hexs(b: bytes) -> str:
    return " ".join("%02x" % x for x in b)


class DryRunTransport:
    """Prints reports instead of sending them. Acks are simulated."""

    def __init__(self, out=None):
        # pythonw has no console (sys.stdout is None): keep the output in memory then.
        self.out = out or sys.stdout or io.StringIO()
        self.sent: list[bytes] = []
        self._sum = 0
        self._data_left = 0

    def set_feature(self, report: bytes) -> None:
        self.sent.append(report)
        print("SET " + hexs(report), file=self.out)
        if self._data_left:
            self._sum += sum(report)
            self._data_left -= 1
        elif report[1] == 0x04 and report[2] in LAYER_COMMAND.values():
            self._sum = 0
            self._data_left = 9

    def get_feature(self, request: bytes) -> bytes:
        ack = bytearray(request)
        ack[4] = 0x01
        if request[1:3] == b"\x04\x02":
            ack[5] = self._sum & 0xFF
            ack[6] = (self._sum >> 8) & 0xFF
        print("ACK " + hexs(ack), file=self.out)
        return bytes(ack)

    def sleep(self, seconds: float) -> None:
        pass

    def close(self) -> None:
        pass


# --- Windows HID through ctypes -------------------------------------------

if sys.platform == "win32":
    _setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    _hid = ctypes.WinDLL("hid", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
                    ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]

    class HIDD_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT),
                    ("ProductID", wintypes.USHORT), ("VersionNumber", wintypes.USHORT)]

    class HIDP_CAPS(ctypes.Structure):
        _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                    ("InputReportByteLength", wintypes.USHORT),
                    ("OutputReportByteLength", wintypes.USHORT),
                    ("FeatureReportByteLength", wintypes.USHORT),
                    ("Reserved", wintypes.USHORT * 17),
                    ("NumberLinkCollectionNodes", wintypes.USHORT),
                    ("NumberInputButtonCaps", wintypes.USHORT),
                    ("NumberInputValueCaps", wintypes.USHORT),
                    ("NumberInputDataIndices", wintypes.USHORT),
                    ("NumberOutputButtonCaps", wintypes.USHORT),
                    ("NumberOutputValueCaps", wintypes.USHORT),
                    ("NumberOutputDataIndices", wintypes.USHORT),
                    ("NumberFeatureButtonCaps", wintypes.USHORT),
                    ("NumberFeatureValueCaps", wintypes.USHORT),
                    ("NumberFeatureDataIndices", wintypes.USHORT)]

    _HANDLE = wintypes.HANDLE
    INVALID_HANDLE_VALUE = _HANDLE(-1).value
    DIGCF_PRESENT = 0x02
    DIGCF_DEVICEINTERFACE = 0x10
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 1
    FILE_SHARE_WRITE = 2
    OPEN_EXISTING = 3
    HIDP_STATUS_SUCCESS = 0x00110000

    _hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
    _hid.HidD_GetAttributes.argtypes = [_HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
    _hid.HidD_GetAttributes.restype = wintypes.BOOLEAN
    _hid.HidD_GetPreparsedData.argtypes = [_HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    _hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
    _hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    _hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
    _hid.HidP_GetCaps.restype = ctypes.c_long
    _hid.HidD_SetFeature.argtypes = [_HANDLE, ctypes.c_void_p, wintypes.ULONG]
    _hid.HidD_SetFeature.restype = wintypes.BOOLEAN
    _hid.HidD_GetFeature.argtypes = [_HANDLE, ctypes.c_void_p, wintypes.ULONG]
    _hid.HidD_GetFeature.restype = wintypes.BOOLEAN
    _setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR,
                                               wintypes.HWND, wintypes.DWORD]
    _setupapi.SetupDiGetClassDevsW.restype = _HANDLE
    _setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        _HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
        ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
    _setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
    _setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        _HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [_HANDLE]
    _kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                      _HANDLE]
    _kernel32.CreateFileW.restype = _HANDLE
    _kernel32.CloseHandle.argtypes = [_HANDLE]


def _hid_paths() -> list[str]:
    guid = GUID()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))
    info = _setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                                          DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if info == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), "SetupDiGetClassDevs failed")
    paths = []
    try:
        i = 0
        while True:
            ifd = SP_DEVICE_INTERFACE_DATA()
            ifd.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not _setupapi.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid),
                                                         i, ctypes.byref(ifd)):
                break
            i += 1
            needed = wintypes.DWORD()
            _setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(ifd), None, 0,
                                                       ctypes.byref(needed), None)
            buf = ctypes.create_string_buffer(needed.value + 8)
            # cbSize of SP_DEVICE_INTERFACE_DETAIL_DATA_W: 8 on 64-bit, 6 on 32-bit
            ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if _setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(ifd), buf,
                                                          needed, None, None):
                paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(info)
    return paths


def find_kn85() -> str:
    """Return the HID path of the KN85 control interface or raise DeviceNotFound."""
    if sys.platform != "win32":
        raise DeviceNotFound("This tool only works on Windows.")
    want = "vid_%04x&pid_%04x" % (VENDOR_ID, PRODUCT_ID)
    for path in _hid_paths():
        low = path.lower()
        if want not in low or INTERFACE not in low:
            continue
        h = _kernel32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                  OPEN_EXISTING, 0, None)
        if h == INVALID_HANDLE_VALUE:
            continue
        try:
            attrs = HIDD_ATTRIBUTES()
            attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
            if not _hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
                continue
            if (attrs.VendorID, attrs.ProductID) != (VENDOR_ID, PRODUCT_ID):
                continue
            pp = ctypes.c_void_p()
            if not _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                continue
            try:
                caps = HIDP_CAPS()
                if _hid.HidP_GetCaps(pp, ctypes.byref(caps)) & 0xFFFFFFFF != HIDP_STATUS_SUCCESS:
                    continue
                if caps.UsagePage == USAGE_PAGE and caps.FeatureReportByteLength == REPORT_LEN:
                    return path
            finally:
                _hid.HidD_FreePreparsedData(pp)
        finally:
            _kernel32.CloseHandle(h)
    raise DeviceNotFound(
        "The Kisnt KN85 keyboard was not found. Connect it with the USB cable "
        "(not the wireless receiver or Bluetooth) and try again. If it is already "
        "connected, unplug the cable, plug it in again, and wait a few seconds.")


class HidTransport:
    def __init__(self, path: str):
        self.path = path
        self.handle = _kernel32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE,
                                            FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                            OPEN_EXISTING, 0, None)
        if self.handle == INVALID_HANDLE_VALUE:
            raise DeviceNotFound("Could not open the keyboard (Windows error %d)."
                                 % ctypes.get_last_error())

    def set_feature(self, report: bytes) -> None:
        buf = ctypes.create_string_buffer(bytes(report), REPORT_LEN)
        if not _hid.HidD_SetFeature(self.handle, buf, REPORT_LEN):
            raise ProtocolError("Sending to the keyboard failed (Windows error %d)."
                                % ctypes.get_last_error())

    def get_feature(self, request: bytes) -> bytes:
        buf = ctypes.create_string_buffer(bytes(request), REPORT_LEN)
        if not _hid.HidD_GetFeature(self.handle, buf, REPORT_LEN):
            raise ProtocolError("Reading the keyboard's reply failed (Windows error %d)."
                                % ctypes.get_last_error())
        return buf.raw[:REPORT_LEN]

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def close(self) -> None:
        if self.handle and self.handle != INVALID_HANDLE_VALUE:
            _kernel32.CloseHandle(self.handle)
            self.handle = None


# ---------------------------------------------------------------------------
# High-level write
# ---------------------------------------------------------------------------


def _command(t, report: bytes) -> bytes:
    t.set_feature(report)
    t.sleep(DELAY)
    ack = t.get_feature(report)
    for _ in range(2):  # the reply may not be ready yet; ask again (never resend)
        if ack[1:3] == report[1:3] and ack[4] == 0x01:
            break
        t.sleep(DELAY)
        ack = t.get_feature(report)
    if ack[1:3] != report[1:3] or ack[4] != 0x01:
        raise ProtocolError("The keyboard did not accept command %02x %02x (reply: %s)."
                            % (report[1], report[2], hexs(ack[:8])))
    return ack


def write_layer(t, layer: str, remaps: dict[int, int]) -> None:
    """Write one whole layer, exactly as the vendor app does."""
    reports = data_reports(remaps)  # validate before touching the device
    want = expected_checksum(remaps)
    _command(t, CMD_BEGIN)
    t.sleep(DELAY)
    _command(t, cmd_layer(layer))
    for r in reports:
        t.sleep(DELAY)
        t.set_feature(r)
    t.sleep(DELAY_BEFORE_FINISH)
    ack = _command(t, CMD_FINISH)
    got = ack[5] | (ack[6] << 8)
    if got != want:
        raise ProtocolError("The keyboard reported checksum %04x, expected %04x for the %s."
                            % (got, want, LAYER_LABEL[layer]))
    t.sleep(DELAY)
    _command(t, CMD_SAVE)


def write_all(t, record: dict[str, dict[int, int]]) -> None:
    """Rewrite both layers (Top first, then Fn, like the vendor app)."""
    for layer in LAYERS:
        write_layer(t, layer, record.get(layer, {}))
        t.sleep(DELAY)


def open_transport(dry_run: bool):
    if dry_run:
        return DryRunTransport()
    return HidTransport(find_kn85())
