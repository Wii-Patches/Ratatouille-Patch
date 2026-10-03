"""Dolphin test lab: an isolated, resettable Dolphin plus the hands and eyes a script needs.

  * its own user folder (config, NAND, saves) rebuilt for every run
  * scripted input through Dolphin's Pipe controller backend (GameCube pad 1 and Wii Remote 1)
  * the GDB stub for reading/writing emulated memory live (game state is the evidence)
"""
import os, shutil, socket, subprocess, time, struct

DOLPHIN = '/Applications/Dolphin.app/Contents/MacOS/Dolphin'
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
import random
GDB_PORT = random.randint(20000, 40000)   # several labs (other sessions) may run at once

GC_BUTTONS = ['A', 'B', 'X', 'Y', 'Z', 'START', 'L', 'R', 'D_UP', 'D_DOWN', 'D_LEFT', 'D_RIGHT']


class Gdb:
    """Minimal GDB remote-serial-protocol client, enough to peek and poke Dolphin."""
    def __init__(self, port=GDB_PORT, timeout=60):
        t0 = time.time()
        while True:
            try:
                self.s = socket.create_connection(('127.0.0.1', port), timeout=5)
                break
            except OSError:
                if time.time() - t0 > timeout:
                    raise
                time.sleep(0.3)
        self.s.settimeout(20)
        self.buf = b''
        self.running = False
        self._cmd('QStartNoAckMode', raw_ok=True) if False else None

    def _send(self, data):
        cs = sum(data.encode()) & 0xFF
        self.s.sendall(('$%s#%02x' % (data, cs)).encode())

    def _recv_packet(self):
        while True:
            i = self.buf.find(b'$')
            j = self.buf.find(b'#', i + 1) if i >= 0 else -1
            if i >= 0 and j >= 0 and len(self.buf) >= j + 3:
                body = self.buf[i + 1:j].decode(errors='replace')
                self.buf = self.buf[j + 3:]
                self.s.sendall(b'+')
                return body
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError('gdb closed')
            self.buf += chunk

    def _drain(self):
        self.s.settimeout(0.3)
        try:
            while True:
                c = self.s.recv(65536)
                if not c: break
                self.buf += c
        except (socket.timeout, BlockingIOError):
            pass
        self.s.settimeout(20)
        self.buf = b''

    def _cmd(self, data):
        self._drain()
        self._send(data)
        # Dolphin's stub acks our packet with '+' and may hold its reply until it sees acks
        # of its own; keep acking until the answer shows up.
        deadline = time.time() + 20
        self.s.settimeout(0.7)
        try:
            while time.time() < deadline:
                i = self.buf.find(b'$')
                j = self.buf.find(b'#', i + 1) if i >= 0 else -1
                if i >= 0 and j >= 0 and len(self.buf) >= j + 3:
                    body = self.buf[i + 1:j].decode(errors='replace')
                    self.buf = self.buf[j + 3:]
                    self.s.sendall(b'+')
                    if body[:3] in ('T05', 'S05') or body.startswith('O'):
                        continue
                    return body
                try:
                    c = self.s.recv(65536)
                    if not c:
                        raise ConnectionError('gdb closed')
                    self.buf += c
                except socket.timeout:
                    self.s.sendall(b'+')
        finally:
            self.s.settimeout(20)
        raise TimeoutError('no gdb reply to ' + data)

    def halt(self):
        if self.running:
            self.s.sendall(b'\x03')
            self.running = False
            return self._recv_packet()
        return None

    def cont(self):
        self._send('c')
        self.running = True

    def stop_reply_wait(self, timeout=60):
        """After cont(): wait for a stop reply (breakpoint hit)."""
        self.s.settimeout(timeout)
        try:
            r = self._recv_packet()
        finally:
            self.s.settimeout(20)
        self.running = False
        return r

    def read(self, addr, n):
        out = b''
        while n > 0:
            k = min(n, 0x400)
            r = self._cmd('m%x,%x' % (addr, k))
            if r.startswith('E'):
                raise IOError('gdb read %08x failed: %s' % (addr, r))
            out += bytes.fromhex(r)
            addr += k; n -= k
        return out

    def write(self, addr, data):
        r = self._cmd('M%x,%x:%s' % (addr, len(data), data.hex()))
        if r != 'OK':
            raise IOError('gdb write %08x failed: %s' % (addr, r))

    def u32(self, addr):
        return struct.unpack('>I', self.read(addr, 4))[0]

    def regs(self):
        r = self._cmd('g')
        b = bytes.fromhex(r)
        return list(struct.unpack('>32I', b[:128]))

    def bp(self, addr):
        r = self._cmd('Z1,%x,4' % addr)
        if r != 'OK':
            raise IOError('breakpoint failed: ' + r)

    def unbp(self, addr):
        self._cmd('z1,%x,4' % addr)

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


class Pipe:
    def __init__(self, path):
        self.path = path
        self.f = None

    def open(self, timeout=30):
        t0 = time.time()
        while not os.path.exists(self.path):
            if time.time() - t0 > timeout:
                raise TimeoutError(self.path)
            time.sleep(0.2)
        fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK) if False else None
        self.f = open(self.path, 'w', buffering=1)

    def send(self, line):
        self.f.write(line + '\n'); self.f.flush()

    def press(self, b):   self.send('PRESS ' + b)
    def release(self, b): self.send('RELEASE ' + b)
    def stick(self, which, x, y):
        """which: MAIN or C; x,y in 0..1 (0.5 centre)"""
        self.send('SET %s %.4f %.4f' % (which, x, y))
    def trig(self, which, v): self.send('SET %s %.4f' % (which, v))
    def neutral(self):
        for b in GC_BUTTONS: self.release(b)
        self.stick('MAIN', .5, .5); self.stick('C', .5, .5)
        self.trig('L', 0); self.trig('R', 0)


def write_ini(path, sections):
    with open(path, 'w') as f:
        for sec, kv in sections.items():
            f.write('[%s]\n' % sec)
            for k, v in kv.items():
                f.write('%s = %s\n' % (k, v))


class Lab:
    def __init__(self, name='lab', gc=True, wiimote_ext='Nunchuk', wiimote=True, gdb=True, sd=None, video='Null'):
        self.dir = os.path.join(ROOT, 'work', name)
        self.user = os.path.join(self.dir, 'user')
        self.gc_enabled, self.ext, self.wiimote, self.use_gdb, self.sd = gc, wiimote_ext, wiimote, gdb, sd
        self.video = video
        self.hkpipe = Pipe(os.path.join(self.user, 'Pipes', 'hk'))
        self.proc = None; self.gdb = None
        self.gcpipe = Pipe(os.path.join(self.user, 'Pipes', 'gc1'))
        self.wmpipe = Pipe(os.path.join(self.user, 'Pipes', 'wm1'))

    def build_config(self):
        shutil.rmtree(self.user, ignore_errors=True)
        os.makedirs(os.path.join(self.user, 'Config'))
        os.makedirs(os.path.join(self.user, 'Pipes'))
        for n in ('gc1', 'wm1', 'hk'):
            os.mkfifo(os.path.join(self.user, 'Pipes', n))     # Dolphin reads the fifos it finds here
        general = {'ISOPaths': '0', 'WirelessMac': '00:17:ab:55:d4:e6'}
        if self.use_gdb: general['GDBPort'] = str(GDB_PORT)
        write_ini(os.path.join(self.user, 'Config', 'Dolphin.ini'), {
            'General': general,
            'Interface': {'SkipNKitWarning': 'True', 'ConfirmStop': 'False', 'UsePanicHandlers': 'False',
                          'OnScreenDisplayMessages': 'False'},
            'Core': {'CPUCore': '1', 'CPUThread': 'False', 'MMU': 'True', 'EmulationSpeed': '0',
                     'OverrideRegionSettings': 'True', 'WiimoteContinuousScanning': 'False',
                     'WiimoteControllerInterface': 'False', 'WiimoteEnableSpeaker': 'False',
                     'AudioBackend': 'No Audio Output', 'SIDevice0': '6' if self.gc_enabled else '0',
                     'SIDevice1': '0', 'SIDevice2': '0', 'SIDevice3': '0', 'EnableCheats': 'False',
                     'WiiSDCard': 'True' if self.sd else 'False', 'SyncOnSkipIdle': 'True'},
            'Input': {'BackgroundInput': 'True'},
            'DSP': {'EnableJIT': 'True'},
            'Display': {'Fullscreen': 'False', 'RenderWindowAutoSize': 'False'},
        })
        if self.sd:
            pass
        write_ini(os.path.join(self.user, 'Config', 'Hotkeys.ini'), {
            'Hotkeys': {'Device': 'Pipe/0/hk', 'General/Take Screenshot': '`Button A`'}})
        write_ini(os.path.join(self.user, 'Config', 'GFX.ini'), {'Settings': {'ShowFPS': 'False', 'VSync': 'False'},
                                                                  'Hardware': {'VSync': 'False'}})
        dev = 'Pipe/0/gc1'
        gc = {'Device': dev}
        for b in ['A', 'B', 'X', 'Y', 'Z', 'Start']:
            gc['Buttons/' + b] = '`Button %s`' % b.upper()
        for n, p in (('Up', 'D_UP'), ('Down', 'D_DOWN'), ('Left', 'D_LEFT'), ('Right', 'D_RIGHT')):
            gc['D-Pad/' + n] = '`Button %s`' % p
        gc['Triggers/L'] = '`Button L`'; gc['Triggers/R'] = '`Button R`'
        gc['Triggers/L-Analog'] = '`Axis L +`'; gc['Triggers/R-Analog'] = '`Axis R +`'
        for stick, nm in (('Main Stick', 'MAIN'), ('C-Stick', 'C')):
            gc[stick + '/Up'] = '`Axis %s Y +`' % nm; gc[stick + '/Down'] = '`Axis %s Y -`' % nm
            gc[stick + '/Left'] = '`Axis %s X -`' % nm; gc[stick + '/Right'] = '`Axis %s X +`' % nm
        write_ini(os.path.join(self.user, 'Config', 'GCPadNew.ini'), {
            'GCPad1': gc, 'GCPad2': {'Device': dev}, 'GCPad3': {'Device': dev}, 'GCPad4': {'Device': dev}})
        wm = {'Device': 'Pipe/0/wm1', 'Source': '1' if self.wiimote else '0', 'Extension': self.ext}
        wm_btn = {'A': 'A', 'B': 'B', '1': 'X', '2': 'Y', '+': 'START', '-': 'Z', 'Home': 'L'}
        if self.ext != 'Classic':          # with a Classic Controller the remote's own buttons stay unbound,
            for k, v in wm_btn.items():    # so every hold bit seen by the game came through the patch
                wm['Buttons/' + k] = '`Button %s`' % v
            for n, p in (('Up', 'D_UP'), ('Down', 'D_DOWN'), ('Left', 'D_LEFT'), ('Right', 'D_RIGHT')):
                wm['D-Pad/' + n] = '`Button %s`' % p
        wm['Nunchuk/Buttons/C'] = '`Button R`'; wm['Nunchuk/Buttons/Z'] = '`Button D_UP`'
        for n, a in (('Up', 'MAIN Y +'), ('Down', 'MAIN Y -'), ('Left', 'MAIN X -'), ('Right', 'MAIN X +')):
            wm['Nunchuk/Stick/' + n] = '`Axis %s`' % a
        wm['Nunchuk/Stick/Calibration'] = '100.00 141.42 100.00 141.42 100.00 141.42 100.00 141.42'
        # classic controller mapped onto the same pipe (only one extension is active at a time)
        cc_btn = {'A': 'A', 'B': 'B', 'X': 'X', 'Y': 'Y', '+': 'START', '-': 'Z', 'Home': 'L'}
        for k, v in cc_btn.items():
            wm['Classic/Buttons/' + k] = '`Button %s`' % v
        for n, p in (('Up', 'D_UP'), ('Down', 'D_DOWN'), ('Left', 'D_LEFT'), ('Right', 'D_RIGHT')):
            wm['Classic/D-Pad/' + n] = '`Button %s`' % p
        for n, a in (('Up', 'MAIN Y +'), ('Down', 'MAIN Y -'), ('Left', 'MAIN X -'), ('Right', 'MAIN X +')):
            wm['Classic/Left Stick/' + n] = '`Axis %s`' % a
        for n, a in (('Up', 'C Y +'), ('Down', 'C Y -'), ('Left', 'C X -'), ('Right', 'C X +')):
            wm['Classic/Right Stick/' + n] = '`Axis %s`' % a
        wm['Classic/Triggers/L'] = '`Button L`'; wm['Classic/Triggers/R'] = '`Button R`'
        wm['Classic/Triggers/L-Analog'] = '`Axis L +`'; wm['Classic/Triggers/R-Analog'] = '`Axis R +`'
        wm['Classic/Buttons/ZL'] = '`Button D_DOWN`'; wm['Classic/Buttons/ZR'] = '`Button D_LEFT`'
        wm['IR/Up'] = '`Axis C Y +`'; wm['IR/Down'] = '`Axis C Y -`'
        wm['IR/Left'] = '`Axis C X -`'; wm['IR/Right'] = '`Axis C X +`'
        write_ini(os.path.join(self.user, 'Config', 'WiimoteNew.ini'), {
            'Wiimote1': wm, 'Wiimote2': {'Source': '0'}, 'Wiimote3': {'Source': '0'},
            'Wiimote4': {'Source': '0'}, 'BalanceBoard': {'Source': '0'}})

    def start(self, image, extra=()):
        self.build_config()
        cmd = [DOLPHIN, '-b', '-u', self.user, '-e', image, '-v', self.video] + list(extra)
        self.log = open(os.path.join(self.dir, 'dolphin.log'), 'w')
        self.proc = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT)
        if self.use_gdb:
            self.gdb = Gdb()
            self.gdb.cont()          # Dolphin waits for the debugger before booting
        if self.gc_enabled:
            self.gcpipe.open()
        if self.wiimote:
            self.wmpipe.open()
        return self

    def screenshot(self, name, wait=8):
        """Capture the emulator's render window (macOS) to <lab>/shots/<name>.png."""
        import Quartz
        best = None
        for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID):
            if w.get('kCGWindowOwnerPID') == self.proc.pid:
                b = w['kCGWindowBounds']; area = b['Width'] * b['Height']
                if '|' not in (w.get('kCGWindowName') or ''):
                    continue                    # the render window's title carries the status line
                if area > 10000 and (best is None or area > best[0]):
                    best = (area, w['kCGWindowNumber'])
        if not best:
            return None
        out = os.path.join(self.dir, 'shots'); os.makedirs(out, exist_ok=True)
        dst = os.path.join(out, name + '.png')
        subprocess.run(['screencapture', '-x', '-o', '-l', str(best[1]), dst], check=False)
        return dst if os.path.exists(dst) else None

    @staticmethod
    def _pngs(root):
        for r, _, fs in os.walk(root):
            for f in fs:
                if f.endswith('.png'): yield os.path.join(r, f)

    def stop(self):
        if self.gdb:
            self.gdb.close()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(10)
            except subprocess.TimeoutExpired: self.proc.kill()
        for p in (self.gcpipe, self.wmpipe):
            try:
                if p.f: p.f.close()
            except Exception: pass

    def __enter__(self): return self
    def __exit__(self, *a): self.stop()
