# -*- coding: utf-8 -*-
"""生成 assets/icon.ico（用渲染器画的角色头图，含多尺寸）。"""
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter, QColor
from PyQt5.QtWidgets import QApplication

from petpet.renderer import PetRenderer, Pose, CANVAS_W, CANVAS_H

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
os.makedirs(ASSETS, exist_ok=True)


def main():
    app = QApplication(sys.argv)
    S = 4
    img = QImage(CANVAS_W * S, CANVAS_H * S, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    PetRenderer().render(p, Pose(expression="cool", action="idle",
                                 props={"sunglasses"}), S)
    p.end()
    # 裁剪头部
    crop = img.copy(int((150 - 105) * S), int((150 - 92) * S),
                    int(210 * S), int(200 * S))
    tmp = os.path.join(ASSETS, "_tmp.png")
    crop.save(tmp)

    from PIL import Image
    base = Image.open(tmp).convert("RGBA")
    base.thumbnail((256, 256), Image.LANCZOS)
    base.save(os.path.join(ASSETS, "icon.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                     (128, 128), (256, 256)])
    os.remove(tmp)
    print("saved assets/icon.ico")


if __name__ == "__main__":
    main()
