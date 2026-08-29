# -*- coding: utf-8 -*-
"""全局热键（可选依赖 keyboard）。缺失时静默降级为仅托盘操作。"""
import threading
import logging

log = logging.getLogger(__name__)

try:
    import keyboard
    _HAVE = True
except Exception:
    _HAVE = False


class Hotkeys:
    def __init__(self, window, pet):
        self.window = window
        self.pet = pet
        self._bindings = {}
        if not _HAVE:
            log.warning("未安装 keyboard，全局热键不可用（可在托盘操作）。")
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            keyboard.add_hotkey(self.window.cfg.get("hotkeys", {}).get("toggle_clickthrough", "ctrl+alt+p"),
                                lambda: self.window.toggle_click_through())
            keyboard.add_hotkey(self.window.cfg.get("hotkeys", {}).get("toggle_hide", "ctrl+alt+h"),
                                lambda: self._toggle_hide())
            keyboard.add_hotkey(self.window.cfg.get("hotkeys", {}).get("poke", "ctrl+alt+s"),
                                lambda: self.pet.poke())
        except Exception as e:
            log.warning("热键注册失败：%s", e)
        keyboard.wait()

    def _toggle_hide(self):
        if self.window.isVisible():
            self.window.hide_pet()
        else:
            self.window.show_pet()
