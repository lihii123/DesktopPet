# -*- coding: utf-8 -*-
"""贴图式角色渲染器 —— 使用用户提供的真人肖像作为桌面宠物。
保留：动作驱动的整体变换（呼吸/拖拽/歪头/挤压）、粒子系统、气泡对话、
表情叠加层（脸红/眨眼/墨镜/惊讶/生气）。
坐标系：逻辑画布 300x430，贴图 280x425 居中放置，贴图底部 y=427 即"脚底"。
"""
import math
import os
import sys
import base64
from dataclasses import dataclass, field
from typing import Tuple, List

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import (QPainter, QColor, QPen, QBrush, QPainterPath,
                         QFont, QFontMetricsF, QPixmap, QImage)

CANVAS_W = 300
CANVAS_H = 430
FEET_Y = 427            # 贴图底部（半身像的"脚底"）
PET_CX = 150            # 宠物水平中心

# 贴图在画布中的位置
IMG_X = 10
IMG_Y = 2
IMG_W = 280
IMG_H = 425

# 变换锚点（胸口附近，作为旋转/挤压中心）
ANCHOR_X = 150
ANCHOR_Y = 285

# 脸部特征点（画布坐标，用于叠加层）
EYE_L = (113, 155)
EYE_R = (180, 155)
CHEEK_L = (100, 193)
CHEEK_R = (193, 193)
MOUTH_PT = (147, 213)
FOREHEAD = (150, 112)


@dataclass
class Pose:
    expression: str = "neutral"      # neutral happy wink pout surprised sleepy tired
                                     # blush sad cool angry love dizz
    action: str = "idle"             # idle walk hang fall sit nap tilt bite sweat
                                     # nod drink dance wave rare stretch
    flip: int = 1                    # 1 面向右 / -1 面向左
    phase: float = 0.0               # 动画相位 0..2π
    look: Tuple[float, float] = (0.0, 0.0)   # 视线跟随 -1..1
    hang_angle: float = 0.0          # 被抓时的身体倾斜（弧度）
    head_tilt: float = 0.0           # 歪头角度（弧度）
    squish: Tuple[float, float] = (1.0, 1.0) # 挤压（落地/呼吸）
    blink: float = 0.0               # 0..1 眨眼闭合程度
    props: set = field(default_factory=set)  # sunglasses / cup / headphones / crown
    blush: float = 0.0               # 0..1 脸红程度
    sweat: float = 0.0               # 0..1 出汗程度
    particles: list = field(default_factory=list)
    bubble_text: str = ""
    bubble_t: float = 0.0            # 气泡剩余时长（秒）
    seed: int = 0


class PetRenderer:
    """贴图渲染器。render(painter, pose) 在 300x430 画布内绘制宠物。"""

    def __init__(self, asset_dir=None):
        self.pixmap = QPixmap()
        # 优先从 base64 内嵌数据加载（最可靠，打包后一定能找到）
        try:
            from .pet_image import PET_PNG_B64
            img_data = base64.b64decode(PET_PNG_B64)
            img = QImage.fromData(img_data, "PNG")
            if not img.isNull():
                self.pixmap = QPixmap.fromImage(img)
                return
        except Exception:
            pass
        # 备用：从文件路径加载
        if asset_dir is None:
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                candidates = [os.path.join(meipass, "assets")]
            else:
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                candidates = ["assets", os.path.join(project_root, "assets")]
            for d in candidates:
                if os.path.exists(os.path.join(d, "pet.png")):
                    asset_dir = d
                    break
        if asset_dir:
            self.pixmap = QPixmap(os.path.join(asset_dir, "pet.png"))

    # ---------------- 入口 ----------------
    def render(self, p: QPainter, pose: Pose, scale: float = 1.0):
        p.save()
        p.scale(scale, scale)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 只有角色本体翻面（表情叠加层随角色一起翻）
        p.save()
        if pose.flip < 0:
            p.translate(CANVAS_W, 0)
            p.scale(-1, 1)
        self._draw_character(p, pose)
        p.restore()
        # 粒子和气泡不翻面，文字始终正向显示
        self._draw_particles(p, pose.particles)
        if pose.bubble_text:
            self._draw_bubble(p, pose)
        p.restore()

    # ---------------- 角色主体（贴图 + 变换） ----------------
    def _draw_character(self, p: QPainter, pose: Pose):
        action = pose.action
        expr = pose.expression

        # 呼吸/行走起伏
        bob = 0.0
        if action in ("idle", "walk", "tilt", "bite", "sit"):
            bob = math.sin(pose.phase) * (2.2 if action == "walk" else 1.2)
        elif action in ("dance", "rare"):
            bob = math.sin(pose.phase * 2.0) * 2.8
        elif action == "nod":
            bob = math.sin(pose.phase * 6.0) * 1.5

        # 视线跟随：整体轻微偏移（模拟看向光标）
        look_x, look_y = pose.look
        shift_x = look_x * 3.5
        shift_y = look_y * 2.0

        # 歪头角度
        tilt = pose.head_tilt
        if action == "tilt":
            tilt = 0.12 * pose.flip
        elif action == "nap":
            tilt = 0.28 * pose.flip
        elif action == "nod":
            tilt = math.sin(pose.phase * 6.0) * 0.09

        # 被抓时倾斜
        hang = action == "hang"

        # 困倦时降低不透明度（模拟疲倦）
        alpha = 255
        if expr in ("sleepy", "tired"):
            alpha = 200
        elif action == "nap":
            alpha = 185

        sx, sy = pose.squish

        p.save()
        # 锚点平移 + 起伏 + 视线偏移
        p.translate(ANCHOR_X + shift_x, ANCHOR_Y + bob + shift_y)

        # 被抓：旋转 + 上提
        if hang:
            p.rotate(math.degrees(pose.hang_angle))
            p.translate(0, -24)

        # 歪头
        if tilt:
            p.rotate(math.degrees(tilt))

        # 挤压（落地/呼吸）
        p.scale(sx, sy)

        # 绘制贴图（左上角相对锚点的偏移）
        dx = IMG_X - ANCHOR_X
        dy = IMG_Y - ANCHOR_Y
        p.setOpacity(alpha / 255.0)
        if not self.pixmap.isNull():
            p.drawPixmap(QPointF(dx, dy), self.pixmap)
        else:
            # fallback：灰色占位矩形
            p.setBrush(QBrush(QColor(200, 200, 210)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(dx, dy, IMG_W, IMG_H), 20, 20)
        p.setOpacity(1.0)

        # 表情叠加层（在贴图之上）
        self._draw_expression_overlays(p, pose)

        p.restore()

    # ---------------- 表情叠加层 ----------------
    def _draw_expression_overlays(self, p: QPainter, pose: Pose):
        expr = pose.expression
        # 叠加层坐标 = 特征点 - 锚点（因为当前坐标系已平移到锚点）
        def rel(pt):
            return (pt[0] - ANCHOR_X, pt[1] - ANCHOR_Y)

        # 眨眼（肤色半透明眼皮）
        if pose.blink > 0 or expr == "wink":
            cover = pose.blink if pose.blink > 0 else 1.0
            if expr == "wink":
                # 只眨左眼
                ex, ey = rel(EYE_L)
                self._draw_eyelid(p, ex, ey, cover)
            else:
                for ep in (EYE_L, EYE_R):
                    ex, ey = rel(ep)
                    self._draw_eyelid(p, ex, ey, cover)

        # 脸红（粉色脸颊，淡而自然）
        if pose.blush > 0 or expr in ("blush", "love"):
            intensity = pose.blush if pose.blush > 0 else (0.6 if expr == "blush" else 0.35)
            a = int(90 * intensity)
            for cp in (CHEEK_L, CHEEK_R):
                cx, cy = rel(cp)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(255, 120, 135, a)))
                p.drawEllipse(QPointF(cx, cy), 15, 9)

        # 墨镜
        if "sunglasses" in pose.props or expr == "cool":
            self._draw_sunglasses(p, rel)

        # 惊讶：嘴旁 "!"
        if expr == "surprised":
            mx, my = rel(MOUTH_PT)
            p.setPen(QPen(QColor(255, 70, 70), 3, Qt.SolidLine, Qt.RoundCap))
            f = QFont("Arial", 18, QFont.Bold)
            p.setFont(f)
            p.drawText(QPointF(mx + 22, my - 8), "!")

        # 生气：额头青筋
        if expr == "angry":
            fx, fy = rel(FOREHEAD)
            p.setPen(QPen(QColor(210, 50, 50), 2.8))
            vx = fx + 22
            vy = fy + 8
            p.drawLine(QPointF(vx, vy), QPointF(vx + 9, vy + 9))
            p.drawLine(QPointF(vx + 9, vy), QPointF(vx, vy + 9))

        # 开心：脸颊淡粉
        if expr == "happy":
            for cp in (CHEEK_L, CHEEK_R):
                cx, cy = rel(cp)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(255, 150, 160, 50)))
                p.drawEllipse(QPointF(cx, cy), 13, 8)

    def _draw_eyelid(self, p, x, y, cover):
        """在眼睛位置画一条细弧线（模拟闭眼/笑眼，真人照片适用）。"""
        if cover < 0.3:
            return
        # 细弧线：向上弯的闭眼线（深棕色，像眼线/睫毛）
        pen = QPen(QColor(60, 48, 44, int(220 * cover)), 2.8, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # 从左到右向上弯的弧线（笑眼）
        p.drawArc(QRectF(x - 16, y - 8, 32, 16), 200 * 16, -140 * 16)
        # 眨眼时下方加一条极淡的肤色阴影（增强闭合感）
        if cover > 0.7:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(240, 214, 198, int(60 * cover))))
            p.drawEllipse(QPointF(x, y + 2), 14, 4)

    def _draw_sunglasses(self, p, rel):
        """在眼睛位置画墨镜。"""
        p.setPen(QPen(QColor(18, 18, 24), 2.2))
        p.setBrush(QBrush(QColor(28, 28, 36, 225)))
        for ep in (EYE_L, EYE_R):
            ex, ey = rel(ep)
            p.drawRoundedRect(QRectF(ex - 19, ey - 11, 38, 22), 10, 10)
        # 鼻梁
        elx = rel(EYE_L)[0]
        erx = rel(EYE_R)[0]
        ey = rel(EYE_L)[1]
        p.drawLine(QPointF(elx + 19, ey), QPointF(erx - 19, ey))
        # 镜腿
        p.drawLine(QPointF(elx - 19, ey - 1), QPointF(elx - 33, ey - 6))
        p.drawLine(QPointF(erx + 19, ey - 1), QPointF(erx + 33, ey - 6))
        # 镜片高光
        p.setBrush(QBrush(QColor(255, 255, 255, 55)))
        p.setPen(Qt.NoPen)
        lx, ly = rel(EYE_L)
        p.drawEllipse(QPointF(lx - 7, ly - 4), 6, 3.5)

    # ---------------- 粒子 ----------------
    def _draw_particles(self, p: QPainter, particles):
        for pt in particles:
            kind = pt.get("kind")
            x, y = pt.get("x", 0), pt.get("y", 0)
            t = pt.get("t", 0.0)
            a = max(0.0, min(1.0, 1.0 - t))
            s = pt.get("s", 1.0)
            if kind == "heart":
                self._draw_heart(p, x, y, 8 * s, QColor(255, 90, 120, int(200 * a)))
            elif kind == "zzz":
                p.setPen(QPen(QColor(120, 130, 180, int(200 * a)), 2.6, Qt.SolidLine, Qt.RoundCap))
                p.setBrush(Qt.NoBrush)
                p.drawText(QRectF(x - 12, y - 12, 24, 24), Qt.AlignCenter, "z")
            elif kind == "sweat":
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(120, 200, 255, int(200 * a))))
                p.drawEllipse(QPointF(x, y), 3.5, 5.5)
            elif kind == "sparkle":
                self._draw_sparkle(p, x, y, 6 * s, QColor(255, 220, 120, int(220 * a)))
            elif kind == "star":
                self._draw_star(p, x, y, 7 * s, QColor(255, 200, 80, int(200 * a)))
            elif kind == "note":
                p.setPen(QPen(QColor(180, 160, 220, int(200 * a)), 2.5))
                p.setBrush(Qt.NoBrush)
                p.drawText(QRectF(x - 10, y - 10, 20, 20), Qt.AlignCenter, "♪")

    def _draw_heart(self, p, cx, cy, size, color):
        path = QPainterPath()
        path.moveTo(cx, cy + size * 0.7)
        path.cubicTo(cx - size * 1.3, cy - size * 0.3, cx - size * 0.6, cy - size * 1.1,
                     cx, cy - size * 0.35)
        path.cubicTo(cx + size * 0.6, cy - size * 1.1, cx + size * 1.3, cy - size * 0.3,
                     cx, cy + size * 0.7)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(path)

    def _draw_sparkle(self, p, cx, cy, r, color):
        p.setPen(QPen(color, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
        p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))

    def _draw_star(self, p, cx, cy, r, color):
        path = QPainterPath()
        for i in range(10):
            ang = math.pi * i / 5 - math.pi / 2
            rad = r if i % 2 == 0 else r * 0.45
            x = cx + math.cos(ang) * rad
            y = cy + math.sin(ang) * rad
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(path)

    # ---------------- 气泡 ----------------
    def _draw_bubble(self, p: QPainter, pose: Pose):
        text = pose.bubble_text
        font = QFont("Microsoft YaHei", 15)
        fm = QFontMetricsF(font)
        pad = 10
        max_w = CANVAS_W - 40
        # 按宽度折行
        lines = []
        cur = ""
        for ch in text:
            if fm.horizontalAdvance(cur + ch) <= max_w - pad * 2:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        text_w = max(fm.horizontalAdvance(l) for l in lines) + pad * 2
        text_h = len(lines) * fm.height() + pad * 2
        bw = min(text_w, max_w)
        bx = (CANVAS_W - bw) / 2
        by = 8
        # 淡入淡出
        alpha = min(1.0, pose.bubble_t * 3) if pose.bubble_t < 3 else min(1.0, (6.0 - pose.bubble_t) * 0.5)
        alpha = max(0.0, min(1.0, alpha))
        if alpha <= 0:
            return
        # 气泡体
        path = QPainterPath()
        path.addRoundedRect(QRectF(bx, by, bw, text_h + 8), 16, 16)
        # 尾巴（指向头顶）
        tail = QPainterPath()
        tail.moveTo(PET_CX - 8, by + text_h + 6)
        tail.quadTo(PET_CX, by + text_h + 24, PET_CX + 10, by + text_h + 6)
        tail.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(235 * alpha)))
        p.drawPath(path)
        p.drawPath(tail)
        # 文字
        p.setPen(QColor(50, 50, 60, int(255 * alpha)))
        p.setFont(font)
        for i, line in enumerate(lines):
            ty = by + pad + i * fm.height() + 2
            p.drawText(QPointF((CANVAS_W - fm.horizontalAdvance(line)) / 2, ty + fm.ascent()), line)
