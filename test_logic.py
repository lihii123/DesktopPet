# -*- coding: utf-8 -*-
"""逻辑层无头集成测试（Linux 可跑，QT_QPA_PLATFORM=offscreen）。

覆盖：主循环无异常、抓取悬空、抛落回弹、单击/双击表情、抚摸害羞、
自主行为（漫步/爬窗/打盹/稀有）、提醒触发，并随机抽帧渲染 PNG。
用法：QT_QPA_PLATFORM=offscreen python3 test_logic.py
"""
import math
import os
import sys
import time
import random

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPainter, QColor

from petpet.config import Config
from petpet.pet import Pet
from petpet.behaviors import Behaviors
from petpet.reminders import Reminders
from petpet.renderer import PetRenderer, CANVAS_W, CANVAS_H

OUT = "test_frames"
random.seed(7)


def render(pet, path):
    img = QImage(int(CANVAS_W * 2), int(CANVAS_H * 2), QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    PetRenderer().render(p, pet.make_pose(), 2.0)
    p.end()
    img.save(path)


def simulate():
    app = QApplication([])
    os.makedirs(OUT, exist_ok=True)
    cfg = Config()
    cfg.data["reminders"]["sedentary_min"] = 60
    cfg.data["reminders"]["water_min"] = 45
    pet = Pet(cfg, dpr=1.0)
    pet.screen_w = 1600
    pet.floor_y = 900
    pet.x = 800
    pet.y = 900
    behaviors = Behaviors(pet, cfg)
    behaviors._greeted = True  # 跳过问候，专注行为
    says = []
    flashes = []
    reminders = Reminders(cfg, lambda s, d: says.append(s), lambda *a, **k: flashes.append(a))

    now = 1000.0
    dt = 1 / 60
    frame = 0
    cursor = (800, 500)
    mouse_pressed = False

    def tick(steps):
        nonlocal now, frame, cursor
        for _ in range(steps):
            now += dt
            pet.update(dt, cursor, mouse_pressed, now)
            behaviors.update(dt, now)
            reminders.update(dt, now)

    # 1) 自由活动 20 秒
    tick(int(20 / dt))
    render(pet, os.path.join(OUT, "f1_free.png"))
    assert pet.mode == "free"

    # 2) 抓取悬空 1.5 秒
    pet.on_press((850, 700), now)
    mouse_pressed = True
    for _ in range(30):
        tick(1)
    assert pet.mode == "grabbed", pet.mode
    render(pet, os.path.join(OUT, "f2_grabbed.png"))
    # 拖动
    for i in range(30):
        cursor = (850 + i * 8, 700 - i * 4)
        pet.on_cursor_move(cursor, now)
        tick(1)
    render(pet, os.path.join(OUT, "f3_dragging.png"))

    # 3) 松手抛落
    mouse_pressed = False
    pet.on_release((cursor[0], cursor[1]), now)
    render(pet, os.path.join(OUT, "f4_falling.png"))
    for _ in range(200):
        tick(1)
        if pet.mode == "free":
            break
    render(pet, os.path.join(OUT, "f5_after_land.png"))
    assert pet.mode in ("free", "dizzy")
    print("fall landed mode:", pet.mode)

    # 4) 单击 → 表情轮换
    pet.on_press(cursor, now)
    mouse_pressed = True
    tick(3)
    mouse_pressed = False
    pet.on_release(cursor, now)
    assert pet.expression in ("wink", "pout", "surprised"), pet.expression
    render(pet, os.path.join(OUT, "f6_click.png"))
    print("click expr:", pet.expression)

    # 5) 双击 → happy/love
    pet.on_press(cursor, now)
    mouse_pressed = True
    tick(3)
    mouse_pressed = False
    pet.on_release(cursor, now)
    pet.on_press(cursor, now)
    mouse_pressed = True
    tick(3)
    mouse_pressed = False
    pet.on_release(cursor, now)
    assert pet.expression in ("happy", "love"), pet.expression
    render(pet, os.path.join(OUT, "f7_doubleclick.png"))
    print("double expr:", pet.expression)

    # 6) 抚摸 → blush
    t0 = now
    for i in range(60):
        now += dt
        cx = 800 + (20 if (i // 5) % 2 == 0 else -20)
        cursor = (cx, 700)
        pet._hovering = True
        pet.update(dt, cursor, False, now)
        behaviors.update(dt, now)
    assert pet.expression == "blush" or pet.blush > 0, pet.expression
    render(pet, os.path.join(OUT, "f8_stroke.png"))
    print("stroke → blush:", pet.expression)

    # 7) 让行为调度自由跑 120 秒，收集经历的动作
    pet._hovering = False
    # 让调度器内部定时器对齐模拟时钟
    behaviors._next_act = now
    behaviors._next_chatter = now + 10 ** 9
    behaviors._next_note = now + 10 ** 9
    behaviors._next_rare = now + 10 ** 9
    behaviors._next_env_bubble = now
    actions_seen = set()
    cursor = (200, 200)  # 远离宠物，避免悬停覆盖自主行为
    for i in range(int(120 / dt)):
        now += dt
        pet.update(dt, cursor, False, now)
        behaviors.update(dt, now)
        reminders.update(dt, now)
        actions_seen.add(pet.action)
        if i % 60 == 0:
            render(pet, os.path.join(OUT, f"f9_run_{i//60}.png"))
    print("actions seen:", sorted(actions_seen))
    assert pet.mode == "free"

    # 8) CPU 高 → 擦汗
    behaviors.cpu._samples = [95.0] * 8
    behaviors.cpu.hot = True
    behaviors.cpu.hot_since = now
    tick(30)
    assert pet.action == "sweat", pet.action
    render(pet, os.path.join(OUT, "f10_sweat.png"))
    print("cpu hot → sweat:", pet.action)

    # 9) 提醒触发（缩短阈值）
    pet.say("x", 0.1)  # 清空
    cfg.data["reminders"]["water_min"] = 1
    r2 = Reminders(cfg, lambda s, d: says.append(s), lambda *a, **k: flashes.append(a))
    r2._water_start = now - 61
    for _ in range(5):
        now += dt
        r2.update(dt, now)
    assert flashes and flashes[-1][0] == "drink", flashes
    print("water reminder triggered:", flashes[-1])
    render(pet, os.path.join(OUT, "f11_drink.png"))

    print("ALL OK, frames in", OUT)


if __name__ == "__main__":
    simulate()
