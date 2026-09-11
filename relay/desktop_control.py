"""Optional, experimental desktop-control layer: lets a task click, type, and scroll
on your actual screen, the way Savr's "computer control" feature does. Off by default.

This module requires a real desktop session (a display) to do anything, so it can't be
exercised in a headless environment or CI — treat it as best-effort and test it
yourself on your machine before trusting it with anything important. Every action
checks the kill switch first, and pyautogui's own fail-safe (slam the mouse into a
screen corner) is left on as a second abort path.

Install with: pip install relay-oss[desktop]
"""

import threading
import time


class KillSwitch:
    """A global hotkey that, once pressed, makes every subsequent DesktopController
    action raise instead of executing. There is no 'un-arm mid-action' — once it
    trips, the current run is meant to stop."""

    def __init__(self, hotkey: str = "ctrl+shift+x"):
        self.hotkey = hotkey
        self._stopped = threading.Event()

    def start(self) -> None:
        try:
            import keyboard
        except ImportError as e:
            raise RuntimeError(
                "The 'keyboard' package is required for the desktop-control kill "
                "switch. Install with: pip install relay-oss[desktop]"
            ) from e
        keyboard.add_hotkey(self.hotkey, self._stopped.set)

    def is_stopped(self) -> bool:
        return self._stopped.is_set()

    def reset(self) -> None:
        self._stopped.clear()


class DesktopController:
    """Thin, deliberately small wrapper around pyautogui. Every public method checks
    the kill switch before acting, so a triggered kill switch stops the run within
    one action, not at the end of the current step."""

    def __init__(self, kill_switch: KillSwitch, action_delay: float = 0.15):
        try:
            import pyautogui
        except ImportError as e:
            raise RuntimeError(
                "The 'pyautogui' package is required for desktop control. "
                "Install with: pip install relay-oss[desktop]"
            ) from e
        self._pg = pyautogui
        self._pg.FAILSAFE = True  # moving the mouse to a screen corner aborts pyautogui itself
        self.kill_switch = kill_switch
        self.action_delay = action_delay

    def _check(self) -> None:
        if self.kill_switch.is_stopped():
            raise KeyboardInterrupt("Relay: kill switch triggered, aborting desktop control")

    def screenshot(self, path: str = None):
        self._check()
        img = self._pg.screenshot()
        if path:
            img.save(path)
        return img

    def click(self, x: int, y: int, button: str = "left") -> None:
        self._check()
        self._pg.moveTo(x, y, duration=0.1)
        time.sleep(self.action_delay)
        self._check()
        self._pg.click(button=button)

    def type_text(self, text: str, interval: float = 0.02) -> None:
        self._check()
        self._pg.typewrite(text, interval=interval)

    def scroll(self, amount: int) -> None:
        self._check()
        self._pg.scroll(amount)
