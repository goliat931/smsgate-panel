"""Nie pozwala komputerowi zasnąć, dopóki panel ma coś do wysłania.

Wygaszenie ekranu niczego nie zatrzymuje, ale w laptopie zwykle po nim przychodzi uśpienie systemu,
a uśpiony komputer nie wysyła SMS-ów. Na Windowsie prosimy system, żeby się nie usypiał (ekran może
zgasnąć). Prośba obowiązuje tylko, gdy w kolejce są wiadomości; potem system zachowuje się jak zwykle.
Ma to być wywoływane z jednego wątku (stan Windows jest per wątek).
"""
import sys

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


class KeepAwake:
    def __init__(self):
        self.on = False

    def set(self, wanted):
        if wanted == self.on:
            return
        self.on = wanted
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if wanted else 0))
