# -*- coding: utf-8 -*-
"""陪伴提醒：久坐 / 喝水 / 番茄钟。"""
import time

from . import dialogue


class Reminders:
    def __init__(self, cfg, on_say, on_flash):
        """on_say(text, dur) / on_flash(kind, dur, **kw) 由调用方桥接到宠物。"""
        self.cfg = cfg
        self.on_say = on_say
        self.on_flash = on_flash
        self._sed_start = time.monotonic()
        self._water_start = time.monotonic()
        self.pomodoro = {"state": "off", "phase": "focus", "remaining": 0.0}

    # ---------------- 每帧 ----------------
    def update(self, dt, now=None):
        if now is None:
            now = time.monotonic()
        r = self.cfg.get("reminders", {})
        sed = int(r.get("sedentary_min", 0))
        wat = int(r.get("water_min", 0))

        if sed > 0 and now - self._sed_start >= sed * 60:
            self._sed_start = now
            self.on_say(dialogue.pick_line("sedentary"), 4.0)
            self.on_flash("dance", 2.5)

        if wat > 0 and now - self._water_start >= wat * 60:
            self._water_start = now
            self.on_say(dialogue.pick_line("water"), 4.0)
            self.on_flash("drink", 4.0, props={"cup"})

        p = self.pomodoro
        if p["state"] == "running":
            p["remaining"] -= dt
            if p["remaining"] <= 0:
                if p["phase"] == "focus":
                    r_ = self.cfg.get("reminders", {})
                    brk = float(r_.get("pomodoro_break", 5))
                    p["phase"] = "break"
                    p["remaining"] = brk * 60
                    self.on_say(dialogue.pick_line("pomodoro_done"), 4.5)
                    self.on_flash("dance", 3.0)
                else:
                    p["state"] = "idle"
                    self.on_say(dialogue.pick_line("pomodoro_break_over"), 3.5)
                    self.on_flash("happy", 2.0)

    # ---------------- 控制 ----------------
    def start_pomodoro(self):
        r = self.cfg.get("reminders", {})
        focus = float(r.get("pomodoro_focus", 25))
        self.pomodoro = {"state": "running", "phase": "focus", "remaining": focus * 60}
        self.on_say(f"番茄钟开始，专注 {int(focus)} 分钟。", 3.5)

    def pause_pomodoro(self):
        if self.pomodoro["state"] == "running":
            self.pomodoro["state"] = "paused"

    def resume_pomodoro(self):
        if self.pomodoro["state"] == "paused":
            self.pomodoro["state"] = "running"

    def reset_pomodoro(self):
        self.pomodoro = {"state": "off", "phase": "focus", "remaining": 0.0}

    def pomodoro_label(self):
        p = self.pomodoro
        if p["state"] == "off":
            return "番茄钟：未开始"
        mins = int(p["remaining"] // 60)
        secs = int(p["remaining"] % 60)
        phase = "专注" if p["phase"] == "focus" else "休息"
        state = {"running": "进行中", "paused": "已暂停"}.get(p["state"], "")
        return f"番茄钟 {phase} {state}：{mins:02d}:{secs:02d}"
