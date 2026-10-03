# Technical notes

## The game
Ratatouille reads input through the KPAD library and insists on `dev_type == 1`
(Nunchuk): buttons from `KPADStatus.hold`, stick from the Nunchuk fields at +0x60/+0x64.

## The hook
`KPADRead` copies one `KPADStatus` (0x84 bytes) per sample into the caller's buffer
(`buf[0]` newest). The hook is the `li r0,0` after that loop, so only the caller's copies
change. Sites per region are found by masked signature (`tools/sig.py`, `src/gen_pad.py`).

## The routine (`src/pad.s`)
* channel number from the channel struct address (0x524 bytes each)
* GameCube pad: SI registers `0xCD006404 + 12*n` (buttons, stick) and `+4` (C-stick)
* Classic Controller: hold word at +0x60, sticks at +0x6c.. / +0x74..
* each clean sample becomes a Nunchuk sample: mapped stick (dead zone 10, full at 90),
  resting acceleration, merged hold/trig/release
* pointer: right stick integrates at 0.02/sample, clamped x ±1.0, y ±0.75; HOME recentres;
  `dpd_valid`, horizon, distance are filled in
* per-channel state (previous hold, pointer) lives at `0x80001D00`

## Layout (`tools/layout.py`)
`0x80001820..0x80001D00` code, `0x80001D00..0x80001D40` state.

## Testing
`tools/lab/unit.py` runs the injected machine code in Unicorn; `lab.py`/`explore.py` drive
Dolphin with pipe input and screenshots.
