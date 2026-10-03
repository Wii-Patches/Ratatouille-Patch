# hook: KPADRead, the `li r0,0` right after its sample loop (the loop that copies one
# finished KPADStatus per sample into the caller's buffer).
#
# Ratatouille only plays with a Wii Remote + Nunchuk: its pad code insists on
# dev_type == 1 (the Nunchuk) and reads the buttons from `hold` and the stick from the
# Nunchuk fields at +0x60/+0x64.  Here, with the samples already in the caller's buffer,
#
#   * a GameCube pad on the same port number as the channel, or
#   * a Classic Controller plugged into the Wii Remote
#
# is rewritten into exactly that, with the right stick steering a pointer (HOME recentres it)
# for the menus and the HOME Menu.  Only the caller's copies are touched, never KPAD's own
# channel struct, so KPAD keeps seeing what the hardware sent.
#
# The SI hardware polls the pads and mirrors the answer into SIC<n>INBUFH
# (0xCD006404 + 12*n, then INBUFL at +4): INBUFH [31] error, [23] always 1 in a real pad
# answer, [29:16] the PAD button word, [15:8] stick X, [7:0] stick Y (128 = centre);
# INBUFL [31:24] C-stick X, [23:16] C-stick Y.
#
# On entry (inside KPADRead): r30 = number of samples, r14 + 0x84 = the buffer (buf[0] is
# the newest sample, buf[n-1] the oldest), r31 = this channel's KPAD struct.  Free:
# r0, r3-r12, f0-f2.  LR is dead here (KPADRead saved it), so helpers are plain `bl`s.
# Careful: `addi rD,0,x` means `li`, so base registers below are never r0.

.macro MAP src, dst                     # if (r9 & src) r10 |= dst
    andi.   11, 9, \src
    beq     1f
    ori     10, 10, \dst
1:
.endm

    stwu    1, -0x60(1)
    cmplwi  30, 0
    beq     done                        # nothing was read
    lis     4, KBASE@ha
    addi    4, 4, KBASE@l
    subf    4, 4, 31
    li      5, 0x524
    divwu   4, 4, 5                     # r4 = channel 0..3
    cmplwi  4, 3
    bgt     done
    slwi    7, 4, 4
    lis     6, DATA@ha
    addi    6, 6, DATA@l
    add     7, 7, 6                     # r7 = this channel's state: previous merged hold, pointer x, y

    mulli   5, 4, 12
    lis     6, 0xCD00
    add     6, 6, 5
    lwz     8, 0x6404(6)                # INBUFH of the port with this channel's number
    li      12, 0                       # r12 = 0: no pad; else the pad's remote bits | 0x80000000
    cmpwi   8, 0
    blt     nopad                       # error / nothing plugged in
    andis.  9, 8, 0x0080
    beq     nopad                       # not a pad answer

    # ---- GameCube pad -> remote bits (r12), sticks on the stack (main x 0x44, y 0x40; C x 0x4c, y 0x48)
    srwi    9, 8, 16                    # PAD buttons
    li      10, 0
    MAP     0x0100, 0x0800              # A       -> A
    MAP     0x0200, 0x0400              # B       -> B
    MAP     0x0400, 0x0200              # X       -> 1
    MAP     0x0800, 0x0100              # Y       -> 2
    MAP     0x1000, 0x0010              # Start   -> +
    MAP     0x0010, 0x1000              # Z       -> -
    MAP     0x0040, 0x2000              # L       -> Nunchuk Z
    MAP     0x0020, 0x4000              # R       -> Nunchuk C
    MAP     0x0008, 0x0008              # D-Up    -> Up
    MAP     0x0004, 0x0004              # D-Down  -> Down
    MAP     0x0001, 0x0001              # D-Left  -> Left
    MAP     0x0002, 0x0002              # D-Right -> Right
    oris    12, 10, 0x8000
    rlwinm  4, 8, 24, 24, 31            # stick X (u8)
    addi    4, 4, -128
    bl      axis
    stfs    0, 0x44(1)                  # main stick x
    rlwinm  4, 8, 0, 24, 31             # stick Y (u8)
    addi    4, 4, -128
    bl      axis
    stfs    0, 0x40(1)                  # main stick y
    lwz     8, 0x6408(6)                # INBUFL: C-stick
    rlwinm  4, 8, 8, 24, 31             # C-stick X
    addi    4, 4, -128
    bl      axis
    stfs    0, 0x4c(1)
    rlwinm  4, 8, 16, 24, 31            # C-stick Y
    addi    4, 4, -128
    bl      axis
    stfs    0, 0x48(1)

nopad:
    # pointer state and constants: f10/f11 = pos x/y, f12 = speed per sample, f13 = x limit, f14 = y limit
    lfs     10, 4(7)
    lfs     11, 8(7)
    lis     0, 0x3CA3                   # 0.02
    ori     0, 0, 0xD70A
    stw     0, 0x50(1)
    lfs     12, 0x50(1)
    lis     0, 0x3F80                   # 1.0
    stw     0, 0x50(1)
    lfs     13, 0x50(1)
    lis     0, 0x3F40                   # 0.75
    stw     0, 0x50(1)
    lfs     14, 0x50(1)
    # ---- walk the samples oldest -> newest (buf[n-1] .. buf[0])
    mulli   3, 30, 0x84
    add     3, 3, 14
    addi    3, 3, 0x84                  # r3 = buf + n*0x84
    mtctr   30
    lwz     4, 0(7)                     # r4 = previous merged hold
next:
    addi    3, 3, -0x84                 # r3 = this sample
    lbz     0, 0x5d(3)
    extsb.  0, 0
    bne     skip                        # not a clean sample (no data / busy)
    cmpwi   12, 0
    bne     usepad
    lbz     0, 0x5c(3)
    cmplwi  0, 2                        # Classic Controller?
    bne     skip

    # Classic Controller: remote bits from its hold word (r9 -> r10), stick from the sample
    lwz     9, 0x60(3)
    li      10, 0
    MAP     0x0010, 0x0800              # A       -> A
    MAP     0x0040, 0x0400              # B       -> B
    MAP     0x0008, 0x0200              # X       -> 1
    MAP     0x0020, 0x0100              # Y       -> 2
    MAP     0x0400, 0x0010              # +       -> +
    MAP     0x1000, 0x1000              # -       -> -
    MAP     0x0800, 0x8000              # HOME    -> HOME
    MAP     0x2080, 0x2000              # L / ZL  -> Nunchuk Z
    MAP     0x0204, 0x4000              # R / ZR  -> Nunchuk C
    MAP     0x0001, 0x0008              # Up      -> Up
    MAP     0x4000, 0x0004              # Down    -> Down
    MAP     0x0002, 0x0001              # Left    -> Left
    MAP     0x8000, 0x0002              # Right   -> Right
    lfs     0, 0x6c(3)                  # left stick x
    lfs     1, 0x70(3)                  # left stick y
    lfs     5, 0x74(3)                  # right stick x
    lfs     6, 0x78(3)                  # right stick y
    b       build
usepad:
    clrlwi  10, 12, 1                   # the pad's remote bits
    lfs     0, 0x44(1)
    lfs     1, 0x40(1)
    lfs     5, 0x4c(1)
    lfs     6, 0x48(1)

build:
    # the sample becomes a Nunchuk's: stick, resting accelerometer, no shoulders
    li      5, 1
    stb     5, 0x5c(3)                  # dev_type = Nunchuk
    stfs    0, 0x60(3)
    stfs    1, 0x64(3)
    lis     0, 0xBF80
    li      5, 0
    stw     5, 0x68(3)                  # acc (0, -1, 0): the Nunchuk at rest
    stw     0, 0x6c(3)
    stw     5, 0x70(3)
    lis     0, 0x3F80
    stw     0, 0x74(3)                  # acc_value 1.0
    stw     5, 0x78(3)                  # acc_speed 0
    stw     5, 0x7c(3)
    stw     5, 0x80(3)

    # the pointer: HOME recentres it, the right stick steers it (y grows downwards)
    andi.   0, 10, 0x8000
    beq     1f
    fsub    10, 10, 10
    fsub    11, 11, 11
1:  fmadds  10, 5, 12, 10               # x += rx * speed
    fnmsubs 11, 6, 12, 11               # y -= ry * speed
    fcmpu   0, 10, 13
    ble     2f
    fmr     10, 13
2:  fneg    7, 13
    fcmpu   0, 10, 7
    bge     3f
    fmr     10, 7
3:  fcmpu   0, 11, 14
    ble     4f
    fmr     11, 14
4:  fneg    7, 14
    fcmpu   0, 11, 7
    bge     5f
    fmr     11, 7
5:  stfs    10, 0x20(3)                 # pos
    stfs    11, 0x24(3)
    li      5, 1
    stb     5, 0x5e(3)                  # dpd_valid
    lis     0, 0x3F80
    stw     0, 0x34(3)                  # horizon (1, 0)
    li      5, 0
    stw     5, 0x38(3)
    stw     0, 0x48(3)                  # dist 1.0
    stw     5, 0x28(3)                  # pointer velocity
    stw     5, 0x2c(3)
    stw     5, 0x30(3)

    # hold / trig / release: the remote's own buttons plus the pad's
    lwz     5, 0(3)
    or      5, 5, 10                    # new hold
    andc    0, 5, 4
    stw     0, 4(3)                     # trig
    andc    0, 4, 5
    stw     0, 8(3)                     # release
    stw     5, 0(3)
    mr      4, 5                        # this sample's hold is the next one's "previous"
skip:
    bdnz    next
    stw     4, 0(7)
    stfs    10, 4(7)
    stfs    11, 8(7)
    b       done

# r4 = signed stick offset -> f0 = normalised value in [-1, 1] with a dead zone.
# Dead zone DEAD, full scale at DEAD + 80 (KMUL = 256 * 64 / 80, rounded up).
axis:
    srawi   11, 4, 31                   # -1 if negative
    xor     5, 4, 11
    subf    5, 11, 5                    # |v|
    cmpwi   5, DEAD
    ble     zero
    addi    5, 5, -DEAD
    mulli   5, 5, KMUL
    srawi   5, 5, 6
    cmpwi   5, 256
    ble     1f
    li      5, 256
1:  xor     5, 5, 11
    subf    4, 11, 5                    # signed again, in 1/256ths
    b       tofloat
zero:
    li      4, 0
tofloat:                                # f0 = r4 / 256.0
    lis     0, 0x4330
    stw     0, 0x38(1)
    xoris   4, 4, 0x8000
    stw     4, 0x3c(1)
    lfd     0, 0x38(1)
    lis     0, 0x4330
    stw     0, 0x20(1)
    lis     0, 0x8000
    stw     0, 0x24(1)
    lfd     2, 0x20(1)
    fsub    0, 0, 2
    lis     0, 0x3B80
    stw     0, 0x28(1)
    lfs     2, 0x28(1)
    fmul    0, 0, 2
    blr

done:
    addi    1, 1, 0x60
    li      0, 0                        # displaced instruction
