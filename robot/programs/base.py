"""
Base class for Eliobot programs.
All programs should inherit from this class.

Convention:
- setup(): init hardware / resources
- loop(): one iteration of the main loop
- run(): calls setup() then loops forever calling loop()

You can still override run() if you want (ex: fully custom).
"""

import time


class Program:
    """Base class for Eliobot programs."""

    def __init__(self):
        self._started = False
        self._timers = {}  # name -> next_due_ms

    # ---------- Lifecycle ----------

    def setup(self):
        """Optional: called once before looping."""
        pass

    def loop(self):
        """
        Optional: called repeatedly.
        If you override only loop(), you get a standard run() automatically.
        """
        time.sleep(0.1)

    def run(self):
        """Default run implementation: setup() then loop forever."""
        if not self._started:
            self._started = True
            self.setup()

        while True:
            self.loop()

    # ---------- Helpers ----------

    def sleep_ms(self, ms: int):
        time.sleep(ms / 1000.0)

    def now_ms(self) -> int:
        # CircuitPython has time.monotonic() float seconds
        return int(time.monotonic() * 1000)

    def every_ms(self, name: str, period_ms: int) -> bool:
        """
        Returns True when a named periodic timer is due.
        Useful for multi-frequency loops without a scheduler.
        """
        t = self.now_ms()
        due = self._timers.get(name, None)
        if due is None or t >= due:
            self._timers[name] = t + int(period_ms)
            return True
        return False