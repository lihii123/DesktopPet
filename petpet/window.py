# -*- coding: utf-8 -*-
"""宠物主窗口：无边框、透明、置顶、不抢焦点；承载渲染与主循环。

鼠标交互：
  按下（停留/拖动）→ 抓取悬空；快速按下松开 → 单击/双击表情；来回抚摸 → 害羞。
  点击穿透开启时，事件全部透传，但视线跟随/悬停反应仍通过全局光标轮询生效。
"""
import time

from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QCursor, QPainter
from PyQt5.QtWidgets import QWidget, QApplication

from . import environment as env
from .renderer import PetRenderer, CANVAS_W, CANVAS_H


class PetWindow(QWidget):
    def __init__(self, pet, behaviors, reminders, cfg, dpr=1.0):
        super().__init__()
        self.pet = pet
        self.behaviors = behaviors
        self.reminders = reminders
        self.cfg = cfg
        self.dpr = dpr
        self._renderer = PetRenderer()
        self._mouse_down = False
        self._last_t = time.monotonic()
        self.click_through = bool(cfg.get("click_through", False))

        # 窗口属性
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.click_through)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        w = int(CANVAS_W * self.pet.scale)
        h = int(CANVAS_H * self.pet.scale)
        self.setFixedSize(w, h)
        self.setMouseTracking(True)

        # 应用初始位置
        x, y, _, _ = self.pet.window_rect()
        self.move(x, y)

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ---------------- 点击穿透 ----------------
    def set_click_through(self, on: bool):
        self.click_through = bool(on)
        self.cfg.data["click_through"] = self.click_through
        self.cfg.save()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.click_through)
        if env.is_windows():
            try:
                import ctypes
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_LAYERED = 0x00080000
                user32 = ctypes.windll.user32
                hwnd = int(self.winId())
                style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
                if self.click_through:
                    style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
                else:
                    style &= ~WS_EX_TRANSPARENT
                user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
            except Exception:
                pass

    def toggle_click_through(self):
        self.set_click_through(not self.click_through)

    # ---------------- 鼠标事件 ----------------
    def mousePressEvent(self, ev):
        if self.click_through:
            return
        if ev.button() == Qt.LeftButton:
            self._mouse_down = True
            gp = ev.globalPos()
            self.pet.on_press((gp.x(), gp.y()), time.monotonic())

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._mouse_down = False
            gp = ev.globalPos()
            self.pet.on_release((gp.x(), gp.y()), time.monotonic())

    def mouseMoveEvent(self, ev):
        if self.click_through:
            return
        gp = ev.globalPos()
        self.pet.on_cursor_move((gp.x(), gp.y()), time.monotonic())

    # ---------------- 主循环 ----------------
    def _tick(self):
        now = time.monotonic()
        dt = min(now - self._last_t, 0.05)
        self._last_t = now

        # 隐藏到托盘时暂停一切动画
        if not self.isVisible():
            return

        cursor = QCursor.pos()
        cp = (cursor.x(), cursor.y())

        # 悬停检测（基于全局光标，点击穿透时也生效）
        self._update_hover(cp)

        # 宠物状态
        self.pet.update(dt, cp, self._mouse_down and not self.click_through, now)

        # 自主行为 + 提醒
        self.behaviors.update(dt, now)
        self.reminders.update(dt, now)

        # 移动窗口到宠物位置
        x, y, _, _ = self.pet.window_rect()
        if (x, y) != (self.pos().x(), self.pos().y()):
            self.move(x, y)

        self.update()

    def _update_hover(self, cp):
        pet = self.pet
        # 交互范围：宠物身体大致区域
        x0 = pet.x - 95 * pet.scale
        x1 = pet.x + 95 * pet.scale
        y0 = pet.y - 300 * pet.scale
        y1 = pet.y + 5 * pet.scale
        pet._hovering = (x0 <= cp[0] <= x1 and y0 <= cp[1] <= y1)

    # ---------------- 绘制 ----------------
    def paintEvent(self, _):
        p = QPainter(self)
        pose = self.pet.make_pose()
        self._renderer.render(p, pose, self.pet.scale)
        p.end()

    # ---------------- 显示/隐藏 ----------------
    def show_pet(self):
        self.show()
        self.raise_()
        from . import dialogue
        self.pet.say(dialogue.pick_line("come_back"), 3.0)

    def hide_pet(self):
        self.hide()
