"""Optional cursor overlay: a small always-on-top marker that follows Relay's
simulated mouse position, so you can see at a glance what the desktop-control layer
is about to click. Best-effort — tkinter's transparency behavior varies by OS, and
this has only been exercised on Linux/X11 and Windows. Skip it entirely if it's not
behaving on your setup; it's cosmetic, not load-bearing for the kill switch."""

import threading
import time


class CursorOverlay:
    def __init__(self, size: int = 16, color: str = "red"):
        self.size = size
        self.color = color
        self._running = False
        self._thread = None
        self._target = (0, 0)

    def move_to(self, x: int, y: int) -> None:
        self._target = (x, y)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", 0.7)
        except tk.TclError:
            pass
        canvas = tk.Canvas(root, width=self.size, height=self.size, highlightthickness=0)
        canvas.pack()
        canvas.create_oval(0, 0, self.size, self.size, fill=self.color, outline="")

        def tick():
            if not self._running:
                root.destroy()
                return
            x, y = self._target
            root.geometry(f"{self.size}x{self.size}+{x - self.size // 2}+{y - self.size // 2}")
            root.after(30, tick)

        tick()
        root.mainloop()
