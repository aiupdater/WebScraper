"""Public session state and a bounded command mailbox; no browser objects cross threads."""
import queue
import threading


class BrowserControl:
    def __init__(self, hidden=True):
        self.hidden = hidden
        self.lock = threading.RLock()
        self.commands = queue.Queue(maxsize=1)
        self.state = dict(visibility='off', captcha=False, pending=False, fallback=False)

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values)
            return dict(self.state)

    def toggle(self):
        with self.lock:
            if self.state['visibility'] == 'off' or self.state['pending']:
                return False
            self.commands.put_nowait('toggle')
            self.state['pending'] = True
            return True

    def reset(self):
        with self.lock:
            while not self.commands.empty():
                self.commands.get_nowait()
            self.state = dict(visibility='off', captcha=False, pending=False, fallback=False)
