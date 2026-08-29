# -*- coding: utf-8 -*-
"""离屏渲染预览：生成角色在各种表情/动作下的 PNG，用于开发调试与展示。

用法：
  python -m petpet.preview [--out 目录] [--sheet]
"""
import math
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter, QColor
from PyQt5.QtWidgets import QApplication

from .renderer import PetRenderer, Pose, CANVAS_W, CANVAS_H

SCALE = 2  # 渲染放大倍率（预览更清晰）


def _render(pose: Pose) -> QImage:
    img = QImage(int(CANVAS_W * SCALE), int(CANVAS_H * SCALE), QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    r = PetRenderer()
    r.render(p, pose, SCALE)
    p.end()
    return img


def make_scene(expression="neutral", action="idle", **kw) -> Pose:
    pose = Pose(expression=expression, action=action, seed=0)
    for k, v in kw.items():
        setattr(pose, k, v)
    return pose


def generate_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    scenes = [
        ("01_neutral", make_scene("neutral", "idle", phase=0.0)),
        ("02_happy", make_scene("happy", "idle", phase=0.0)),
        ("03_wink", make_scene("wink", "idle", phase=0.5)),
        ("04_pout", make_scene("pout", "idle", phase=0.0)),
        ("05_surprised", make_scene("surprised", "idle", phase=0.0)),
        ("06_blush", make_scene("blush", "idle", phase=0.0, blush=1.0,
                                particles=[{"kind": "heart", "x": 118, "y": 130, "t": 0.3, "s": 1.0}])),
        ("07_sleepy", make_scene("sleepy", "nap", head_tilt=0.3, phase=1.0,
                                 particles=[{"kind": "zzz", "x": 200, "y": 120, "t": 0.4, "s": 1.0}])),
        ("08_tired", make_scene("tired", "idle", phase=0.0)),
        ("09_cool_sunglasses", make_scene("cool", "idle", props={"sunglasses"}, phase=0.0)),
        ("10_bite_chain", make_scene("neutral", "bite", phase=0.0)),
        ("11_hang", make_scene("surprised", "hang", hang_angle=0.25, phase=1.2)),
        ("12_walk", make_scene("neutral", "walk", phase=1.2)),
        ("13_sit", make_scene("happy", "sit", phase=1.5)),
        ("14_dance", make_scene("happy", "dance", phase=1.0)),
        ("15_crown_rare", make_scene("happy", "rare", props={"crown"}, phase=0.0)),
        ("16_headphones", make_scene("neutral", "idle", props={"headphones"}, phase=0.0)),
        ("17_drink", make_scene("neutral", "drink", props={"cup"}, phase=0.0)),
        ("18_bubble", make_scene("neutral", "idle", bubble_text="早，别赖床了，我的睫毛都被你赖掉了。", bubble_t=2.0)),
        ("19_dizz", make_scene("dizz", "idle", phase=0.0,
                               particles=[{"kind": "star", "x": 90, "y": 140, "t": 0.4, "s": 1.0},
                                          {"kind": "star", "x": 210, "y": 120, "t": 0.6, "s": 1.0}])),
        ("20_love", make_scene("love", "idle", blush=1.0, phase=0.0,
                               particles=[{"kind": "heart", "x": 96, "y": 118, "t": 0.2, "s": 1.2},
                                          {"kind": "heart", "x": 210, "y": 108, "t": 0.4, "s": 1.0}])),
    ]
    for name, pose in scenes:
        img = _render(pose)
        path = os.path.join(out_dir, f"{name}.png")
        img.save(path)
        print("saved:", path)


def generate_sheet(out_path):
    """拼一张大图方便整体预览。"""
    from PyQt5.QtGui import QImage, QPainter, QFont, QColor, QPen
    cols, rows = 5, 4
    cell_w, cell_h = int(CANVAS_W * SCALE), int(CANVAS_H * SCALE)
    sheet = QImage(cols * cell_w, rows * cell_h, QImage.Format_ARGB32)
    sheet.fill(QColor(246, 244, 250))
    p = QPainter(sheet)
    names = [
        "neutral", "happy", "wink", "pout", "surprised",
        "blush", "nap", "tired", "cool(sg)", "bite",
        "hang", "walk", "sit", "dance", "crown",
        "headphones", "drink", "bubble", "dizz", "love",
    ]
    maker = [
        make_scene("neutral", "idle"),
        make_scene("happy", "idle"),
        make_scene("wink", "idle"),
        make_scene("pout", "idle"),
        make_scene("surprised", "idle"),
        make_scene("blush", "idle", blush=1.0),
        make_scene("sleepy", "nap", head_tilt=0.3),
        make_scene("tired", "idle"),
        make_scene("cool", "idle", props={"sunglasses"}),
        make_scene("neutral", "bite"),
        make_scene("surprised", "hang", hang_angle=0.25),
        make_scene("neutral", "walk", phase=1.2),
        make_scene("happy", "sit", phase=1.5),
        make_scene("happy", "dance", phase=1.0),
        make_scene("happy", "rare", props={"crown"}),
        make_scene("neutral", "idle", props={"headphones"}),
        make_scene("neutral", "drink", props={"cup"}),
        make_scene("neutral", "idle", bubble_text="早，别赖床了～"),
        make_scene("dizz", "idle"),
        make_scene("love", "idle", blush=1.0),
    ]
    from PyQt5.QtGui import QFont, QColor, QPen
    r = PetRenderer()
    p.setRenderHint(QPainter.Antialiasing, True)
    for idx, (name, pose) in enumerate(zip(names, maker)):
        cx = (idx % cols) * cell_w
        cy = (idx // cols) * cell_h
        p.save()
        p.translate(cx, cy)
        p.scale(SCALE, SCALE)
        # 底
        p.fillRect(0, 0, CANVAS_W, CANVAS_H, QColor(246, 244, 250))
        r.render(p, pose, 1.0)
        p.restore()
        # 标签
        p.setPen(QColor(90, 90, 100))
        f = QFont("Microsoft YaHei", 16)
        p.setFont(f)
        p.drawText(cx + 12, cy + 30, name)
    p.end()
    sheet.save(out_path)
    print("saved sheet:", out_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    out = sys.argv[1] if len(sys.argv) > 1 else "preview_out"
    generate_all(out)
    if "--sheet" in sys.argv:
        generate_sheet(os.path.join(out, "_sheet.png"))
