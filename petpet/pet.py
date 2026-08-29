# -*- coding: utf-8 -*-
"""宠物核心：状态机 + 轻量物理 + 交互识别（与平台无关，方便本地测试）。

位置约定：pet.x / pet.y 是「脚底中心」的屏幕坐标；pet.y 最大为地面 floor_y。
渲染约定：窗口把宠物脚底中心放到 (pet.x, pet.y)。
"""
import math
import random
import time

from . import environment as env
from .renderer import Pose, CANVAS_W, CANVAS_H, FEET_Y, PET_CX
from . import dialogue

GRAVITY = 2600.0       # 像素/秒²
BOUNCE = 0.42          # 落地回弹系数
WALK_SPEED = 52.0      # 像素/秒
HEAD_ABOVE_FEET = 257.0  # 头中心距脚底（贴图版：脚底427 - 头中心约170）

SINGLE_CLICK_EXPRS = ["wink", "pout", "surprised"]
DOUBLE_CLICK_EXPRS = ["happy", "love"]


class Pet:
    def __init__(self, config, dpr=1.0):
        self.cfg = config
        self.scale = float(config.get("scale", 1.0))
        self.dpr = max(dpr, 1.0)
        env_floor = env.get_floor_y() / self.dpr
        env_w = env.get_screen_width() / self.dpr
        self.screen_w = env_w
        self.floor_y = env_floor

        self.x = self.screen_w / 2
        self.y = self.floor_y
        self.facing = 1

        # 状态机
        self.mode = "free"          # free / grabbed / falling / dizzy
        self.expression = "neutral"
        self.action = "idle"        # idle walk sit nap tilt bite hang fall dance rare sweat nod drink stretch
        self.phase = random.uniform(0, math.pi * 2)
        self.look = (0.0, 0.0)
        self.hang_angle = 0.0
        self.head_tilt = 0.0
        self.squish = (1.0, 1.0)
        self.props = set()
        self.blush = 0.0
        self.sweat = 0.0

        # 眼睛
        self._blink_t = random.uniform(2.0, 4.5)
        self._blinking = 0.0        # 0..1

        # 气泡
        self.bubble_text = ""
        self.bubble_t = 0.0
        self.bubble_dur = 4.0

        # 粒子
        self.particles = []

        # 物理
        self.vx = 0.0
        self.vy = 0.0
        self._squish_v = 0.0

        # 交互
        self._hovering = False
        self._hover_t = 0.0
        self._hover_kind = ""
        self._press_pending = False
        self._press_t = 0.0
        self._press_pos = (0, 0)
        self._grab_t = 0.0
        self._recent_pt = []        # (t, x, y) 用于甩动测速
        self._stroke_buf = []       # [(t, x)] 抚摸检测
        self._last_click_t = -10.0
        self._last_expr_t = 0.0
        self._dizzy_t = 0.0

        # 行为（由 behaviors.py 调度写入）
        self.behavior = {"kind": "idle", "target_x": self.x, "x": self.x,
                         "top_y": 0, "start": time.monotonic(), "dur": 0}
        self._beh_lock = False      # 交互期间锁定行为执行

        # 展示用 pose 缓存
        self._tick_time = time.monotonic()

    # ---------------- 对外只读 ----------------
    def window_rect(self):
        w = CANVAS_W * self.scale
        h = CANVAS_H * self.scale
        x = self.x - PET_CX * self.scale
        y = self.y - FEET_Y * self.scale
        return (int(x), int(y), int(w), int(h))

    def head_pos(self):
        return (self.x, self.y - HEAD_ABOVE_FEET * self.scale)

    # ---------------- 交互入口（窗口事件调用） ----------------
    def on_press(self, cursor, t):
        self._press_pending = True
        self._press_t = t
        self._press_pos = cursor
        self._recent_pt = [(t, cursor[0], cursor[1])]
        self._stroke_buf = []

    def on_release(self, cursor, t):
        self._press_pending = False
        if self.mode == "grabbed":
            # 甩动测速
            vx, vy = self._estimate_throw(t)
            moved = math.hypot(cursor[0] - self._press_pos[0],
                               cursor[1] - self._press_pos[1])
            if moved < 18 * self.scale and abs(vx) < 60 and abs(vy) < 60:
                # 原地捏一下 → 当作点击，不丢出
                self.mode = "free"
                self.y = self.floor_y
                self._handle_click(t)
            else:
                self._release_throw(vx, vy)
        else:
            # 快速按下松开 → 单击/双击
            self._handle_click(t)

    def on_cursor_move(self, cursor, t):
        if self.mode == "grabbed":
            self._recent_pt.append((t, cursor[0], cursor[1]))
            if len(self._recent_pt) > 6:
                self._recent_pt.pop(0)

    def poke(self):
        self.say(dialogue.pick_line("poke"), 3.2)
        self.expression = "surprised"
        self._spawn_particles("sparkle", 6, (PET_CX, 170))

    # ---------------- 点击 ----------------
    def _handle_click(self, t):
        if t - self._last_click_t < 0.32:
            self._last_click_t = t
            expr = random.choice(DOUBLE_CLICK_EXPRS)
            self.expression = expr
            self.action = "idle"
            if expr == "love":
                self.blush = 1.0
                self._spawn_particles("heart", 6, (PET_CX, 150))
            else:
                self.say(dialogue.pick_line("happy"), 2.8)
        else:
            self._last_click_t = t
            expr = random.choice(SINGLE_CLICK_EXPRS)
            self.expression = expr
            self.action = "idle"
            self.blush = 0.6 if expr == "wink" else 0.0
            self.say(dialogue.pick_line(expr), 2.8)

    # ---------------- 物理 ----------------
    def _estimate_throw(self, t):
        if len(self._recent_pt) >= 2:
            (t0, x0, y0), (t1, x1, y1) = self._recent_pt[0], self._recent_pt[-1]
            dt = max(t1 - t0, 0.05)
            vx = (x1 - x0) / dt
            vy = (y1 - y0) / dt
            return max(-900, min(900, vx)), max(-1400, min(900, vy))
        return 0.0, 0.0

    def _engage_grab(self, cursor, t):
        self.mode = "grabbed"
        self._grab_t = t
        self.expression = "surprised"
        self.action = "hang"
        self._spawn_particles("sweat", 2, (PET_CX, 150))
        if random.random() < 0.35:
            self.say(dialogue.pick_line("grab"), 2.6)

    def _release_throw(self, vx, vy):
        self.mode = "falling"
        self.vx = vx
        self.vy = vy
        self.action = "fall"
        self.expression = "surprised"
        self.say(dialogue.pick_line("release"), 2.4)

    def _land(self):
        self.mode = "dizzy"
        self.expression = "dizz"
        self.action = "idle"
        self._dizzy_t = 0.0
        self.squish = (1.25, 0.72)
        self._spawn_particles("star", 5, (PET_CX, 150))

    # ---------------- 气泡 / 粒子 ----------------
    def say(self, text, dur=4.0):
        if not text:
            return
        self.bubble_text = text
        self.bubble_t = 0.0
        self.bubble_dur = dur

    def _spawn_particles(self, kind, n, center, spread=70):
        cx, cy = center
        for _ in range(n):
            self.particles.append({
                "kind": kind, "x": cx + random.uniform(-spread, spread),
                "y": cy + random.uniform(-30, 30),
                "t": random.uniform(0, 0.3), "s": random.uniform(0.8, 1.3),
                "vy": random.uniform(-60, -20),
            })

    # ---------------- 行为控制（behaviors 调用） ----------------
    def set_behavior(self, beh: dict):
        self.behavior = beh

    @property
    def interactive(self):
        return self.mode in ("free", "dizzy")

    # ---------------- 主循环 ----------------
    def update(self, dt, cursor, mouse_pressed, t=None):
        if t is None:
            t = time.monotonic()
        self._tick_time = t
        self.phase += dt * 2.2

        # ---- 视线跟随（始终生效）----
        self._update_look(cursor)

        # ---- 交互状态机 ----
        if mouse_pressed and self.mode == "free":
            # 按下时间/位移达标 → 抓取
            if self._press_pending and (t - self._press_t > 0.12 or
                                        math.hypot(cursor[0] - self._press_pos[0],
                                                   cursor[1] - self._press_pos[1]) > 10 * self.scale):
                self._engage_grab(cursor, t)

        if self.mode == "grabbed":
            self._update_grabbed(cursor, t)
        elif self.mode == "falling":
            self._update_falling(dt)
        elif self.mode == "dizzy":
            self._update_dizzy(dt)
        else:
            self._update_free(dt, cursor, t)

        # ---- 眨眼 ----
        self._update_blink(dt)

        # ---- 粒子老化 ----
        self._update_particles(dt)

        # ---- 气泡计时 ----
        if self.bubble_text:
            self.bubble_t += dt
            if self.bubble_t > self.bubble_dur:
                self.bubble_text = ""

        # ---- 挤压恢复 ----
        sx, sy = self.squish
        if sx != 1.0 or sy != 1.0:
            nsx = 1.0 + (sx - 1.0) * math.exp(-6 * dt)
            nsy = 1.0 + (sy - 1.0) * math.exp(-6 * dt)
            if abs(nsx - 1.0) < 0.01:
                nsx, nsy = 1.0, 1.0
            self.squish = (nsx, nsy)

        # ---- 脸红衰减 ----
        if self.blush > 0:
            self.blush = max(0.0, self.blush - dt * 0.9)

        # ---- 汗衰减 ----
        if self.sweat > 0:
            self.sweat = max(0.0, self.sweat - dt * 0.6)

        # 边界
        margin = 40 * self.scale
        self.x = max(margin, min(self.screen_w - margin, self.x))
        self.y = min(self.floor_y, max(-400, self.y))

    # ---------------- 视线 ----------------
    def _update_look(self, cursor):
        hx, hy = self.head_pos()
        dx = (cursor[0] - hx) / (260 * self.scale)
        dy = (cursor[1] - hy) / (260 * self.scale)
        m = math.hypot(dx, dy)
        if m > 1:
            dx, dy = dx / m, dy / m
        self.look = (dx, dy)

    # ---------------- 抓取 ----------------
    def _update_grabbed(self, cursor, t):
        self.action = "hang"
        self.expression = "surprised"
        # 身体挂在光标下方，带一点摆动
        dt = max(t - self._grab_t, 0.001)
        # 速度（用于摆角）
        vx, vy = self._estimate_throw(t)
        sway = math.sin((t - self._grab_t) * 4.0) * 0.04
        self.hang_angle = max(-0.45, min(0.45, vx * 0.0012 + sway))
        self.x = cursor[0] + math.sin(self.hang_angle) * 60 * self.scale
        self.y = min(self.floor_y + 300, cursor[1] + 250 * self.scale)
        # 快速甩动 → 挣扎
        if abs(vx) > 500 and random.random() < 0.1:
            self.expression = "tired"
            if random.random() < 0.3:
                self.say(dialogue.pick_line("grab"), 2.4)
        self.phase += dt * 6

    # ---------------- 下落 ----------------
    def _update_falling(self, dt):
        self.action = "fall"
        self.expression = "surprised"
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= math.exp(-1.2 * dt)
        if self.y >= self.floor_y:
            self.y = self.floor_y
            if abs(self.vy) > 150:
                self.vy = -self.vy * BOUNCE
                self.x = max(40, min(self.screen_w - 40, self.x))
                # 落地冲击
                self.squish = (1.3, 0.7)
                self._spawn_particles("star", 4, (PET_CX, 360))
            else:
                self.vy = 0.0
                self.vx = 0.0
                self._land()

    # ---------------- 晕眩 ----------------
    def _update_dizzy(self, dt):
        self._dizzy_t += dt
        if self._dizzy_t > 0.7:
            self.mode = "free"
            self.expression = "neutral"
            self.action = "idle"

    # ---------------- 自由活动 ----------------
    def _update_free(self, dt, cursor, t):
        # 悬停检测（窗口会先判断是否在范围内再置 _hovering）
        if self._hovering:
            self._hover_t += dt
            if self._hover_t > 0.55 and self.action in ("idle", "tilt", "bite"):
                self._update_hover(cursor)
        else:
            self._hover_t = 0.0
            self._hover_kind = ""
            if self.action in ("tilt", "bite"):
                self.action = "idle"

        # 抚摸检测
        if self._hovering:
            self._stroke_buf.append((t, cursor[0]))
            if len(self._stroke_buf) > 12:
                self._stroke_buf.pop(0)
            if self._detect_stroke():
                self.expression = "blush"
                self.action = "idle"
                self.blush = 1.0
                self._spawn_particles("heart", 6, (PET_CX, 150))
                self.say(dialogue.pick_line("stroke"), 3.0)
                self._stroke_buf = []
                self._stroke_cooldown = t + 4.0

        # 悬停/抚摸时暂停自主行为
        if self._hovering:
            return

        # 行为执行
        self._execute_behavior(dt)

    def _update_hover(self, cursor):
        hx, hy = self.head_pos()
        # 光标在嘴部区域 → 咬链条；否则歪头
        if hy + 10 * self.scale < cursor[1] < hy + 80 * self.scale:
            if self.action != "bite" and random.random() < 0.5:
                self.action = "bite"
                self.head_tilt = 0.0
                if random.random() < 0.25:
                    self.say(dialogue.pick_line("bite"), 2.4)
            elif self.action == "idle":
                self.action = "bite"
        else:
            if self.action != "tilt":
                self.action = "tilt"
                self.head_tilt = 0.0
                if random.random() < 0.25:
                    self.say(dialogue.pick_line("hover"), 2.4)

    def _detect_stroke(self):
        if len(self._stroke_buf) < 6:
            return False
        if hasattr(self, "_stroke_cooldown") and self._tick_time < self._stroke_cooldown:
            return False
        # 统计方向反转次数
        rev = 0
        prev_dir = 0
        for i in range(1, len(self._stroke_buf)):
            dx = self._stroke_buf[i][1] - self._stroke_buf[i - 1][1]
            if abs(dx) < 2:
                continue
            d = 1 if dx > 0 else -1
            if prev_dir != 0 and d != prev_dir:
                rev += 1
            prev_dir = d
        span = self._stroke_buf[-1][0] - self._stroke_buf[0][0]
        return rev >= 3 and span < 1.6

    # ---------------- 行为执行 ----------------
    def _execute_behavior(self, dt):
        beh = self.behavior
        kind = beh.get("kind", "idle")
        now = time.monotonic()
        # 道具只来源于当前行为，切换行为时自动清理
        self.props = set(beh.get("props", set()))

        if kind == "walk":
            tx = beh["target_x"]
            ty = beh.get("top_y", self.floor_y)
            self._move_toward(tx, ty, dt)
        elif kind == "sit":
            tx = beh["target_x"]
            ty = beh.get("top_y", self.floor_y)
            if abs(tx - self.x) > 8 or abs(ty - self.y) > 8:
                self._move_toward(tx, ty, dt)
            else:
                self.x = tx
                self.y = ty
                self.action = "sit"
                self.phase += dt * 1.6
        elif kind == "nap":
            tx = beh["target_x"]
            ty = beh.get("top_y", self.floor_y)
            if abs(tx - self.x) > 8 or abs(ty - self.y) > 8:
                self._move_toward(tx, ty, dt)
            else:
                self.x = tx
                self.y = ty
                self.action = "nap"
                self.expression = "sleepy"
                self.head_tilt = 0.3 * self.facing
                if random.random() < dt * 0.5:
                    self._spawn_particles("zzz", 1, (PET_CX + 45, 140))
        elif kind == "rare":
            self.action = beh.get("pose", "dance")
            self.props = beh.get("props", set())
            self.expression = "happy"
            if self.action in ("dance", "rare"):
                self.phase += dt * 3.0
            if random.random() < dt * 1.2:
                self._spawn_particles("sparkle", 1, (PET_CX + random.uniform(-60, 60), 150))
        elif kind == "sweat":
            self.action = "sweat"
            self.expression = "tired"
            self.sweat = 1.0
            if random.random() < dt * 0.3:
                self._spawn_particles("sweat", 1, (PET_CX - 30, 150))
        elif kind == "nod":
            self.action = "nod"
            self.expression = "happy"
        elif kind == "drink":
            self.action = "drink"
            self.props.add("cup")
            if random.random() < dt * 0.4:
                self._spawn_particles("sparkle", 1, (PET_CX + 100, 230))
        elif kind == "idle":
            self.action = "idle"
            self.expression = "neutral"
        else:
            self.action = "idle"

    def _move_toward(self, tx, ty, dt):
        """向 (tx,ty) 移动（水平步行 / 纵向跳跃或下落）。"""
        dx = tx - self.x
        dy = ty - self.y
        if abs(dx) < 6 and abs(dy) < 6:
            self.x, self.y = tx, ty
            self.action = "idle"
            return
        step = WALK_SPEED * self.scale * dt
        if abs(dx) > 6:
            self.x += math.copysign(step, dx)
            self.facing = 1 if dx > 0 else -1
        if abs(dy) > 4:
            vstep = step * 1.8
            self.y += math.copysign(vstep, dy)
        self.action = "walk"

    # ---------------- 眨眼 ----------------
    def _update_blink(self, dt):
        if self.expression in ("wink", "happy", "love", "sleepy", "dizz"):
            self._blinking = 0.0
            return
        if self._blinking > 0:
            self._blinking += dt * 9
            if self._blinking > 1.0:
                self._blinking = 0.0
                self._blink_t = random.uniform(2.0, 5.5)
        else:
            self._blink_t -= dt
            if self._blink_t <= 0:
                self._blinking = 0.05

    # ---------------- 粒子 ----------------
    def _update_particles(self, dt):
        alive = []
        for pt in self.particles:
            pt["t"] += dt * 0.5
            pt["y"] += (pt.get("vy", 0) or 0) * dt
            if pt["t"] < 1.0:
                alive.append(pt)
        self.particles = alive

    # ---------------- 渲染快照 ----------------
    def make_pose(self) -> Pose:
        return Pose(
            expression=self.expression,
            action=self.action,
            flip=self.facing,
            phase=self.phase,
            look=self.look,
            hang_angle=self.hang_angle,
            head_tilt=self.head_tilt,
            squish=self.squish,
            blink=self._blinking,
            props=set(self.props),
            blush=self.blush,
            sweat=self.sweat,
            particles=[dict(x) for x in self.particles],
            bubble_text=self.bubble_text,
            bubble_t=self.bubble_t,
            seed=0,
        )

    # 供 behaviors 用
    def clear_props(self):
        self.props = set()
