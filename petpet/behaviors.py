# -*- coding: utf-8 -*-
"""自主行为调度器：时段问候、漫步、爬窗坐顶、打盹、稀有动作、闲谈、便签，
以及环境联动（CPU 擦汗 / 低电量犯困 / 音乐点头）。"""
import random
import time

from . import environment as env
from . import dialogue
from .renderer import PET_CX


class Behaviors:
    def __init__(self, pet, cfg):
        self.pet = pet
        self.cfg = cfg
        self.cpu = env.CpuMonitor()
        self.battery = env.BatteryMonitor()

        self._greeted = False
        self._next_act = time.monotonic() + 1.5
        self._next_chatter = time.monotonic() + random.uniform(90, 180)
        self._next_note = time.monotonic() + random.uniform(180, 300)
        self._next_rare = time.monotonic() + random.uniform(150, 260)
        self._next_env_bubble = time.monotonic()
        self._music_timer = 0.0
        self._override = None        # 当前环境覆盖行为
        self._override_until = 0.0
        self._last_bubble_kind = ""

    # ---------------- 每帧调用 ----------------
    def update(self, dt, now=None):
        if now is None:
            now = time.monotonic()
        self.cpu.sample()
        self.battery.sample()

        if not self._greeted:
            self._greet(now)
            self._greeted = True

        # 环境覆盖（CPU/低电量/音乐）优先
        if self._handle_environment(now):
            return

        # 稀有动作彩蛋
        if self.cfg.get("rare_enabled", True) and now >= self._next_rare:
            self._next_rare = now + random.uniform(200, 360)
            if self.pet.interactive:
                self._do_rare(now)

        # 常规决策
        if now >= self._next_act and self.pet.interactive and not self._override:
            self._decide(now)
            self._next_act = now + self._act_interval()

        # 闲谈 / 便签（低优先级，仅自由时）
        if self.pet.interactive and not self._override:
            if now >= self._next_chatter:
                self._next_chatter = now + random.uniform(120, 240)
                self.pet.say(dialogue.pick_line("idle"), 3.5)
            if now >= self._next_note and self.cfg.get("note_enabled", True) \
                    and self.cfg.get("note_text", "").strip():
                self._next_note = now + random.uniform(240, 420)
                self._show_note(now)

    # ---------------- 时段问候 ----------------
    def _greet(self, now):
        line = dialogue.greeting_for_hour(int(time.localtime().tm_hour))
        if line:
            self.pet.say(line, 4.5)

    # ---------------- 环境联动 ----------------
    def _handle_environment(self, now):
        pet = self.pet
        if self.cfg.get("cpu_sweat", True) and self.cpu.hot:
            pet.set_behavior({"kind": "sweat", "start": now, "dur": 3})
            if now >= self._next_env_bubble:
                self._next_env_bubble = now + 30
                pet.say(dialogue.pick_line("cpu_high"), 3.5)
            return True

        if self.cfg.get("battery_tired", True) and self.battery.low_battery:
            if now >= self._next_env_bubble:
                self._next_env_bubble = now + 60
                pet.say(dialogue.pick_line("battery_low"), 3.5)
                pet.expression = "tired"
            if random.random() < 0.4 and pet.interactive:
                pet.set_behavior({"kind": "nap", "target_x": pet.x,
                                  "top_y": pet.floor_y, "start": now, "dur": 20})
            return True

        if self.cfg.get("music_nod", True) and env.is_music_playing():
            self._music_timer -= 1
            if self._music_timer <= 0:
                self._music_timer = random.randint(4, 9)
                if pet.interactive:
                    pet.set_behavior({"kind": "nod", "start": now, "dur": 1.5})
            return True  # 音乐时暂停漫步决策（保持点头节奏）

        return False

    # ---------------- 稀有动作 ----------------
    def _do_rare(self, now):
        r = random.random()
        if r < 0.35:
            pet = self.pet
            pet.set_behavior({"kind": "rare", "pose": "rare", "props": {"crown"},
                              "start": now, "dur": 6})
            pet.say(dialogue.pick_line("rare_ultimate"), 3.5)
        elif r < 0.7:
            pet = self.pet
            pet.set_behavior({"kind": "rare", "pose": "idle", "props": {"sunglasses"},
                              "start": now, "dur": 6})
            pet.say(dialogue.pick_line("rare_sunglasses"), 3.5)
        else:
            pet = self.pet
            pet.set_behavior({"kind": "rare", "pose": "dance", "props": set(),
                              "start": now, "dur": 6})
            pet.say(dialogue.pick_line("rare_dance"), 3.5)
        # 稀有动作结束后需要清道具
        pet.props = set()

    # ---------------- 常规决策 ----------------
    def _decide(self, now):
        pet = self.pet
        hour = int(time.localtime().tm_hour)
        night = hour >= 23 or hour < 6

        # 找前台窗口顶（物理像素 → 逻辑像素）
        win = env.get_active_window_rect()
        if win:
            win = tuple(v / pet.dpr for v in win)
        can_climb = win is not None and win[1] > 150 and (win[2] - win[0]) > 300
        if night:
            # 深夜：多在原地打盹
            if random.random() < 0.55:
                pet.set_behavior({"kind": "nap", "target_x": pet.x,
                                  "top_y": pet.floor_y, "start": now, "dur": random.uniform(30, 90)})
            else:
                pet.set_behavior({"kind": "idle", "start": now, "dur": random.uniform(6, 12)})
            return

        roll = random.random()
        if can_climb and roll < 0.30:
            left, top, right, _ = win
            tx = random.uniform(left + 90, right - 90)
            pet.set_behavior({"kind": "sit", "target_x": tx, "top_y": top,
                              "start": now, "dur": random.uniform(30, 70)})
        elif roll < 0.55:
            tx = random.uniform(90, max(150, pet.screen_w - 90))
            pet.set_behavior({"kind": "walk", "target_x": tx, "top_y": pet.floor_y,
                              "start": now, "dur": random.uniform(4, 8)})
        elif roll < 0.85:
            pet.set_behavior({"kind": "idle", "start": now, "dur": random.uniform(4, 9)})
        else:
            # 偶尔爬窗打盹
            if can_climb:
                left, top, right, _ = win
                tx = random.uniform(left + 90, right - 90)
                pet.set_behavior({"kind": "nap", "target_x": tx, "top_y": top,
                                  "start": now, "dur": random.uniform(20, 50)})
            else:
                pet.set_behavior({"kind": "idle", "start": now, "dur": random.uniform(4, 9)})

    def _act_interval(self):
        return random.uniform(6, 12)

    # ---------------- 便签 ----------------
    def _show_note(self, now):
        text = self.cfg.get("note_text", "").strip()
        if not text:
            return
        note = text if len(text) <= 30 else text[:29] + "…"
        self.pet.say("便签：" + note, 5.0)

    # ---------------- 供外部（提醒模块）设置临时行为 ----------------
    def flash_action(self, kind, dur=3.0, **kw):
        """插入一个一次性行为（如喝水/伸展/番茄钟庆祝），结束后由下一次决策接管。"""
        beh = {"kind": kind, "start": time.monotonic(), "dur": dur}
        beh.update(kw)
        self.pet.set_behavior(beh)
        self._next_act = time.monotonic() + dur + 1.0
