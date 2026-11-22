# Kisnt KN85 key-remap protocol (reverse engineered 2026-11-22)

Keyboard: Kisnt KN85, USB VID 0C45 PID 8006 (2.4G receiver: 0C45 FEFE; alt IDs 05AC 024F).
Source of truth for key numbers: `layouts/rgb-keyboard.xml` in the vendor driver (key_index per key). The same table is in `kn85_protocol.py` as `PHYSICAL_KEYS`.
Driver package: KN85 Textured Black Driver 1.0.5.0 (Inno Setup, signed by Chinese FINDER (Dongguan) Technology).

## Transport

- Interface MI_02, vendor usage page 0xFF13, 65-byte feature reports (report ID 0 + 64 bytes).
- Every command: HidD_SetFeature(cmd), then HidD_GetFeature to read the ack (same header, byte 4 = 01).
- About 37 ms between reports.

## Commands (bytes after report ID 00)

- `04 18` : begin. Ack `04 18 00 01`.
- `04 11 00 00 00 00 00 00 09` : write TOP layer, 9 data reports follow.
- `04 27 00 00 00 00 00 00 09` : write FN layer, 9 data reports follow.
- 9 data reports, no ack between them: 8 x 64 bytes = 512 bytes = 128 keys x 4 bytes, indexed by key_index.
  The 9th report is all zero except its last two bytes `aa 55`.
- `04 02` : finish. Ack bytes 5-6 are a little-endian 16-bit sum of every byte of the 9 data reports (`ff 00` = 0x00ff for all-default, since aa + 55 = ff; `66 01` = 0x0166 with one remap, since ff + 02 + 65 = 166). Inferred from these two data points; kn85-remap checks it after every layer.
- `04 f0` : final/save. Ack `04 f0 00 01`.

## Key entry (4 bytes)

- `00 00 00 00` = key keeps its default.
- `02 00 <HID usage> 00` = send keyboard usage. Example: Applications = `02 00 65 00`.

## Verified

Fn layer, key_index 98 (right Ctrl) = `02 00 65 00` makes Fn + right Ctrl send VK_APPS (0x5D). Confirmed with a
low-level key listener on 2026-11-22.

## Cautions

- Each write replaces the whole layer. The keyboard did not report its current map back in our traces, so a tool
  must keep its own record and rewrite everything.
- Switching to the Fn Layer tab in the vendor app rewrote both layers with zeros (its stored profile).
- Fn key itself is key_index 96, HID code 0xAF in the layout file. Fn is handled inside the keyboard and never reaches Windows.
- Unknown: macro and lighting commands, other entry types (media keys, mouse), multimedia icons row.
- Full trace: `tests/data/trace-fnlayer-app.log`. `HidD_SetFeature` lines are writes; `IOCTL-OUT b0192` lines are the GetFeature replies.
