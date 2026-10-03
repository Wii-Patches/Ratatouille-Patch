"""Where the injected code lives.

The patch is one hook: one instruction in the game is replaced by a branch to a
routine that does the work, runs the displaced instruction and branches back.
The static build parks the routine (and a few words of state) in one new text
section at CAVE_BASE -- the Wii's boot-time scratch area, which this game never
touches (checked by tools/verify.py: no access to 0x8000_1800..0x8000_3000).
The first 0x20 bytes are skipped: the word at 0x80001800 is overwritten by the OS.
"""
CAVE_BASE = 0x80001820
CAVE_LIMIT = 0x80003000

PAD_BASE = 0x80001820         # the controller routine
PAD_END = 0x80001D00
DATA_BASE = 0x80001D00        # per-channel state: 4 x 16 bytes: previous hold, pointer x, y
DATA_END = 0x80001D40

WINDOWS = {'pad': (PAD_BASE, DATA_END)}
