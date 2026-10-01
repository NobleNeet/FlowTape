"""Linux X11 XTEST input: OS pointer/key events, never DOM/WebDriver actions.

Install the optional native-test extra; XTEST must already exist in the VM.
Coordinates come from read-only browser inspection in the acceptance harness.
"""

from time import sleep
import subprocess

from Xlib import X, XK, display, protocol
from Xlib.ext import xtest


class NativeInput:
    def __init__(self):
        self.display = display.Display()
        if not self.display.has_extension('XTEST'):
            raise RuntimeError('X11 XTEST is required for native input acceptance')
        self.original_engine = subprocess.check_output(['ibus', 'engine'], text=True).strip()
        subprocess.run(['ibus', 'engine', 'xkb:jp::jpn'], check=True, capture_output=True)

    def keycode(self, key):
        symbol = XK.string_to_keysym(key)
        if not symbol and len(key) == 1:
            symbol = ord(key)
        code = self.display.keysym_to_keycode(symbol)
        if not code:
            raise ValueError('Key unavailable: ' + key)
        return code

    def press(self, key):
        code = self.keycode(key)
        xtest.fake_input(self.display, X.KeyPress, code)
        xtest.fake_input(self.display, X.KeyRelease, code)
        self.display.sync()
        sleep(.025)

    def chord(self, *keys):
        codes = [self.keycode(key) for key in keys]
        for code in codes:
            xtest.fake_input(self.display, X.KeyPress, code)
        for code in reversed(codes):
            xtest.fake_input(self.display, X.KeyRelease, code)
        self.display.sync()
        sleep(.025)

    def type(self, text):
        for char in text:
            code = self.keycode(char)
            symbol = XK.string_to_keysym(char) or ord(char)
            mapping = self.display.get_keyboard_mapping(code, 1)[0]
            if mapping[0] != symbol and mapping[1] == symbol:
                # Respect the VM's actual map, including Japanese keyboards.
                shift = self.keycode('Shift_L')
                xtest.fake_input(self.display, X.KeyPress, shift)
                xtest.fake_input(self.display, X.KeyPress, code)
                xtest.fake_input(self.display, X.KeyRelease, code)
                xtest.fake_input(self.display, X.KeyRelease, shift)
            else:
                xtest.fake_input(self.display, X.KeyPress, code)
                xtest.fake_input(self.display, X.KeyRelease, code)
            self.display.sync()
            sleep(.008)

    def click(self, x, y, button=1, control=False):
        xtest.fake_input(self.display, X.MotionNotify, x=int(x), y=int(y))
        if control:
            xtest.fake_input(self.display, X.KeyPress, self.keycode('Control_L'))
        xtest.fake_input(self.display, X.ButtonPress, button)
        xtest.fake_input(self.display, X.ButtonRelease, button)
        if control:
            xtest.fake_input(self.display, X.KeyRelease, self.keycode('Control_L'))
        self.display.sync()
        sleep(.03)

    def activate_edge(self):
        root = self.display.screen().root
        clients = root.get_full_property(self.display.intern_atom('_NET_CLIENT_LIST_STACKING'), X.AnyPropertyType)
        found = []
        for xid in clients.value:
            window = self.display.create_resource_object('window', int(xid))
            if 'microsoft-edge' in ' '.join(window.get_wm_class() or ()).lower():
                found.append(window)
        if len(found) != 1:
            raise RuntimeError(f'Expected one isolated Edge client, found {len(found)}')
        window = found[0]
        root.send_event(protocol.event.ClientMessage(window=window, client_type=self.display.intern_atom('_NET_ACTIVE_WINDOW'),
                        data=(32, [1, X.CurrentTime, 0, 0, 0])), event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self.display.sync()
        sleep(.15)

    def close(self):
        try:
            subprocess.run(['ibus', 'engine', self.original_engine], capture_output=True)
            actual = subprocess.check_output(['ibus', 'engine'], text=True).strip()
            if actual != self.original_engine:
                raise RuntimeError('Original keyboard engine was not restored')
        finally:
            self.display.close()
