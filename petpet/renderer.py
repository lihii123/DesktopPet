# -*- coding: utf-8 -*-
"""程序化角色渲染器 —— 把「潮酷少年」画成 Q 版桌面宠物。

所有视觉均用 QPainter 矢量绘制，因此可以做到：
  视线跟随（瞳孔偏移）、眨眼、表情切换、抓取悬空、落回挤压、
  坐姿晃腿、打盹 Zzz、擦汗、墨镜、戴耳机、举水杯、跳舞、大招……
全部平滑可控、且能无限扩展，这是贴图式宠物做不到的"耐玩度"。

坐标系说明（逻辑画布 300x430，宠物脚底基线 y=418）：
  * 宠物本体约在 y 110~420，头顶上方 y 0~110 留给气泡/粒子。
  * 窗口外只需调用 render(painter, pose)，自带缩放与翻面处理。
"""
import math
import random
from dataclasses import dataclass, field
from typing import Tuple, List

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import (QPainter, QColor, QPen, QBrush, QPainterPath,
                         QRadialGradient, QFont, QFontMetricsF)

CANVAS_W = 300
CANVAS_H = 430
FEET_Y = 418          # 脚底基线
PET_CX = 150          # 宠物水平中心

# ---------- 调色板 ----------
SKIN = QColor(255, 232, 220)
SKIN_SH = QColor(244, 214, 198)          # 肤色阴影
BLUSH = QColor(255, 148, 138, 150)
EYE_SHADOW = QColor(255, 176, 190, 90)   # 粉调眼影
HAIR = QColor(26, 26, 34)
HAIR_DARK = QColor(16, 16, 22)
HAIR_HI = QColor(186, 196, 216)          # 浅色挑染（灰蓝）
EYE = QColor(46, 38, 56)
EYE_HI = QColor(255, 255, 255)
BROW = QColor(60, 52, 66)
MOUTH = QColor(196, 88, 88)
MOUTH_SH = QColor(150, 56, 56)
SHIRT = QColor(250, 250, 253)
SHIRT_SH = QColor(228, 229, 237)
PANTS = QColor(44, 46, 58)
SHOES = QColor(252, 252, 254)
SHOES_ACC = QColor(226, 228, 238)
CHAIN = QColor(198, 202, 214)
CHAIN_D = QColor(150, 154, 168)
PENDANT = QColor(224, 184, 72)
NECK = QColor(247, 220, 206)


# 表情 → 脸部绘制参数
# eye: normal / happy / wink / away / surprised / sleepy / tired / sad / angry / love / dizz / closed
# mouth: smile / open / pout / surprise / line / wavy / frown / smirk / omega / cat
@dataclass
class Pose:
    expression: str = "neutral"      # neutral happy wink pout surprised sleepy tired
                                     # blush sad cool angry love dizz
    action: str = "idle"             # idle walk hang fall sit nap tilt bite sweat nod drink
                                     # dance wave stretch rare
    flip: int = 1                    # 1 面向右 / -1 面向左
    phase: float = 0.0               # 动画相位 0..2π
    look: Tuple[float, float] = (0.0, 0.0)   # 瞳孔跟随 -1..1
    hang_angle: float = 0.0          # 被抓时的身体倾斜（弧度）
    head_tilt: float = 0.0           # 歪头角度（弧度）
    squish: Tuple[float, float] = (1.0, 1.0) # 挤压（落地/呼吸）
    blink: float = 0.0               # 0..1 眨眼闭合程度
    props: set = field(default_factory=set)  # sunglasses / cup / headphones / crown / water
    blush: float = 0.0               # 0..1 脸红程度
    sweat: float = 0.0               # 0..1 出汗程度
    particles: list = field(default_factory=list)
    bubble_text: str = ""
    bubble_t: float = 0.0            # 气泡剩余时长（秒）
    seed: int = 0


def _rgba(c: QColor, a: int):
    return QColor(c.red(), c.green(), c.blue(), a)


def _ell(p: QPainter, cx, cy, rx, ry, color, outline=None, ow=1.0, alpha=None):
    c = _rgba(color, alpha) if alpha is not None else color
    p.setPen(QPen(outline, ow) if outline else Qt.NoPen)
    p.setBrush(QBrush(c))
    p.drawEllipse(QPointF(cx, cy), rx, ry)


def _rr(p: QPainter, x, y, w, h, r, color, outline=None, ow=1.0, alpha=None):
    c = _rgba(color, alpha) if alpha is not None else color
    p.setPen(QPen(outline, ow) if outline else Qt.NoPen)
    p.setBrush(QBrush(c))
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def _cap(p: QPainter, x1, y1, x2, y2, r, color, outline=None, ow=1.0, alpha=None):
    """胶囊形线段（四肢/身体）。"""
    c = _rgba(color, alpha) if alpha is not None else color
    p.setPen(QPen(outline, ow) if outline else Qt.NoPen)
    p.setBrush(QBrush(c))
    p.drawRoundedRect(QRectF(min(x1, x2) - r, min(y1, y2) - r,
                             abs(x2 - x1) + 2 * r, abs(y2 - y1) + 2 * r), r, r)


def _arc_mouth(p: QPainter, cx, cy, rx, ry, start, span, color, w=2.6):
    pen = QPen(color, w, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(cx - rx, cy - ry, rx * 2, ry * 2), start * 16, span * 16)


class PetRenderer:
    """渲染器。render(painter, pose) 在 300x430 画布内绘制宠物。"""

    # ---------------- 入口 ----------------
    def render(self, p: QPainter, pose: Pose, scale: float = 1.0):
        p.save()
        p.scale(scale, scale)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 全局翻面：水平镜像（面向相反方向）
        if pose.flip < 0:
            p.translate(CANVAS_W, 0)
            p.scale(-1, 1)
        self._draw_character(p, pose)
        self._draw_particles(p, pose.particles)
        if pose.bubble_text:
            self._draw_bubble(p, pose)
        p.restore()

    # ---------------- 角色主体 ----------------
    def _draw_character(self, p: QPainter, pose: Pose):
        # 整体微动：呼吸/行走起伏（压缩 y）
        bob = 0.0
        if pose.action in ("idle", "walk", "tilt", "bite"):
            bob = math.sin(pose.phase) * (1.4 if pose.action == "walk" else 1.0)
        sx, sy = pose.squish
        p.translate(PET_CX, 0)
        p.scale(sx, sy * (1 + bob * 0.004))
        p.translate(-PET_CX, 0)

        hang = pose.action == "hang"
        if hang:
            # 被抓：绕头顶附近旋转 + 整体上提
            p.translate(PET_CX, 130)
            p.rotate(math.degrees(pose.hang_angle))
            p.translate(-PET_CX, -130)
            p.translate(0, -36)

        # 身体/腿根据动作做姿态
        self._draw_legs(p, pose)
        self._draw_body(p, pose)
        self._draw_arms(p, pose)
        self._draw_neck_chain(p, pose)
        self._draw_head(p, pose)
        self._draw_props(p, pose)
        if pose.blush > 0:
            self._draw_blush(p, pose)
        if pose.sweat > 0:
            self._draw_sweat(p, pose)

    # ---------------- 腿 ----------------
    def _draw_legs(self, p: QPainter, pose: Pose):
        action = pose.action
        if action == "hang":
            # 悬空挣扎：两腿下垂 + 晃动
            wig = math.sin(pose.phase * 5.0) * 6
            _cap(p, 136, 348, 130 + wig, 402, 13, PANTS)
            _cap(p, 164, 348, 170 - wig, 402, 13, PANTS)
            _ell(p, 130 + wig * 0.7, 404, 15, 9, SHOES, SHOES_ACC, 1.2)
            _ell(p, 170 - wig * 0.7, 404, 15, 9, SHOES, SHOES_ACC, 1.2)
            return
        if action == "sit":
            # 坐在窗沿：腿前伸，晃腿
            sw = math.sin(pose.phase * 2.0) * 10
            _cap(p, 128, 368, 116, 388 + sw, 13, PANTS)
            _cap(p, 172, 368, 184, 388 - sw, 13, PANTS)
            _ell(p, 114, 392 + sw, 15, 9, SHOES, SHOES_ACC, 1.2)
            _ell(p, 186, 392 - sw, 15, 9, SHOES, SHOES_ACC, 1.2)
            return
        if action == "fall":
            # 下落时腿收起
            _cap(p, 134, 352, 132, 376, 13, PANTS)
            _cap(p, 166, 352, 168, 376, 13, PANTS)
            return
        # 站立/行走：双腿交替
        step = 0.0
        if action == "walk":
            step = math.sin(pose.phase) * 6
        elif action in ("dance", "rare"):
            step = math.sin(pose.phase * 2) * 8
        _cap(p, 135, 322, 133 + step, 396, 14, PANTS)
        _cap(p, 165, 322, 167 - step, 396, 14, PANTS)
        _ell(p, 133 + step * 0.6, 400, 16, 9, SHOES, SHOES_ACC, 1.2)
        _ell(p, 167 - step * 0.6, 400, 16, 9, SHOES, SHOES_ACC, 1.2)

    # ---------------- 身体（白 T） ----------------
    def _draw_body(self, p: QPainter, pose: Pose):
        action = pose.action
        if action == "sit":
            y0, y1 = 320, 372   # 坐姿躯干被压缩
        elif action in ("hang", "fall"):
            y0, y1 = 312, 372
        else:
            y0, y1 = 306, 396
        # 躯干
        path = QPainterPath()
        path.moveTo(108, y0)
        path.quadTo(PET_CX, y0 - 10, 192, y0)
        path.lineTo(192, y1)
        path.quadTo(PET_CX, y1 + 8, 108, y1)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(SHIRT))
        p.drawPath(path)
        # 右侧阴影（增加立体）
        sh = QPainterPath()
        sh.moveTo(160, y0)
        sh.lineTo(192, y0)
        sh.lineTo(192, y1)
        sh.quadTo(PET_CX, y1 + 8, 168, y1)
        sh.closeSubpath()
        p.setBrush(QBrush(_rgba(SHIRT_SH, 110)))
        p.drawPath(sh)
        # 胸口小字母印花（呼应参考图 "LEA"）
        if action not in ("hang", "fall"):
            p.setPen(QPen(QColor(150, 150, 165), 7, Qt.SolidLine, Qt.RoundCap))
            f = QFont("Arial", 16, QFont.Bold)
            p.setFont(f)
            p.drawText(QRectF(128, 330, 60, 26), Qt.AlignCenter, "LEA")

    # ---------------- 手臂 ----------------
    def _draw_arms(self, p: QPainter, pose: Pose):
        action = pose.action
        # 肩部位置
        ly, ry = 308, 308
        if action == "hang":
            # 挣扎：双手向上抓
            w1 = math.sin(pose.phase * 5.0) * 4
            w2 = math.cos(pose.phase * 5.0) * 4
            _cap(p, 112, 306, 100, 282 + w1, 11, SHIRT)
            _ell(p, 98, 280 + w1, 9, 9, SKIN)
            _cap(p, 188, 306, 200, 282 + w2, 11, SHIRT)
            _ell(p, 202, 280 + w2, 9, 9, SKIN)
            return
        if action == "sit":
            # 撑在窗沿
            _cap(p, 112, 316, 100, 336, 11, SHIRT)
            _ell(p, 98, 338, 9, 9, SKIN)
            _cap(p, 188, 316, 200, 336, 11, SHIRT)
            _ell(p, 202, 338, 9, 9, SKIN)
            return
        if action == "fall":
            _cap(p, 112, 312, 104, 342, 11, SHIRT)
            _ell(p, 102, 344, 9, 9, SKIN)
            _cap(p, 188, 312, 196, 342, 11, SHIRT)
            _ell(p, 198, 344, 9, 9, SKIN)
            return
        if action in ("dance", "rare"):
            sw = math.sin(pose.phase * 2.5)
            _cap(p, 112, 306, 104, 344 + sw * 8, 11, SHIRT)
            _ell(p, 102, 346 + sw * 8, 9, 9, SKIN)
            _cap(p, 188, 306, 196, 344 - sw * 8, 11, SHIRT)
            _ell(p, 198, 346 - sw * 8, 9, 9, SKIN)
            return
        if action == "drink":
            # 右手举杯到嘴边
            _cap(p, 112, 308, 106, 344, 11, SHIRT)
            _ell(p, 104, 346, 9, 9, SKIN)
            _cap(p, 188, 306, 190, 280, 11, SHIRT)
            return
        # 站立/行走/歪头：手臂自然或轻摆
        swing = math.sin(pose.phase) * 5 if action == "walk" else 0
        _cap(p, 112, 308, 106, 350 + swing, 11, SHIRT)
        _ell(p, 104, 352 + swing, 9, 9, SKIN)
        _cap(p, 188, 308, 194, 350 - swing, 11, SHIRT)
        _ell(p, 196, 352 - swing, 9, 9, SKIN)

    # ---------------- 项链 ----------------
    def _draw_neck_chain(self, p: QPainter, pose: Pose):
        sway = math.sin(pose.phase) * 1.2 if pose.action in ("idle", "walk") else 0
        bite = pose.action == "bite"
        # 短链（choker）
        _arc_mouth(p, PET_CX, 228, 30, 10, 0, 180, CHAIN_D, w=3.0)
        # 长链：从颈侧下垂，bite 时引到嘴边
        if bite:
            path = QPainterPath()
            path.moveTo(132, 234)
            path.cubicTo(128, 260, 122, 268, 118, 278)  # 引到左下嘴角附近
            p.setPen(QPen(CHAIN, 2.6, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            _ell(p, 118, 280, 3, 3, PENDANT)
        else:
            path = QPainterPath()
            path.moveTo(130, 234)
            path.cubicTo(134, 262, 140 + sway, 280, 138 + sway, 300)
            p.setPen(QPen(CHAIN, 2.6, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            _ell(p, 138 + sway, 304, 4, 4, PENDANT)

    # ---------------- 头 + 发 + 脸 ----------------
    def _draw_head(self, p: QPainter, pose: Pose):
        # 头部整体旋转（歪头/打盹）
        tilt = pose.head_tilt
        if pose.action == "tilt":
            tilt = 0.18 * pose.flip
        elif pose.action == "nap":
            tilt = 0.30 * pose.flip
        elif pose.action == "nod":
            tilt = math.sin(pose.phase * 6) * 0.10
        if tilt:
            p.translate(PET_CX, 218)
            p.rotate(math.degrees(tilt))
            p.translate(-PET_CX, -218)

        hx, hy = PET_CX, 214          # 头中心
        R = 92                        # 头半径

        # 后发（耳侧垂发，营造层次）
        _cap(p, hx - 82, hy - 26, hx - 76, hy + 36, 13, HAIR_DARK)
        _cap(p, hx + 76, hy - 26, hx + 82, hy + 36, 13, HAIR_DARK)

        # 脸部（皮肤圆）
        _ell(p, hx, hy, R, R * 0.96, SKIN)

        # 颈部
        _rr(p, 136, 296, 28, 22, 10, NECK)

        # 脸
        self._draw_face(p, pose, hx, hy)

        # 前发（刘海 + 顶发 + 挑染 + 呆毛）
        self._draw_hair_front(p, pose, hx, hy, R)

    def _draw_hair_front(self, p: QPainter, pose: Pose, hx, hy, R):
        top = hy - R * 0.96
        # ---- 主发型：锯齿顶 + 两侧鬓发 + 额头波浪刘海（不遮眼睛）----
        path = QPainterPath()
        path.moveTo(hx - 84, hy - 6)
        # 顶部锯齿发尖（从左到右）
        n = 9
        for i in range(n + 1):
            t = i / n
            x = hx - 84 + 168 * t
            y = top - 16 - (abs(math.sin(t * math.pi * 2.4)) * 9 + abs(math.sin(t * math.pi)) * 8)
            path.lineTo(x, y)
        # 右侧鬓发
        path.lineTo(hx + 86, hy - 4)
        path.quadTo(hx + 94, hy + 26, hx + 82, hy + 56)
        # 下边缘：从右额角沿额头（波浪）到左额角
        path.quadTo(hx + 58, hy + 40, hx + 30, hy - 28)
        path.quadTo(hx + 15, hy - 14, hx, hy - 32)
        path.quadTo(hx - 15, hy - 14, hx - 30, hy - 28)
        path.quadTo(hx - 58, hy + 40, hx - 82, hy + 56)
        # 左侧鬓发回到起点
        path.quadTo(hx - 94, hy + 26, hx - 84, hy - 6)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(HAIR))
        p.drawPath(path)

        # 几缕更长的碎刘海（垂到眉上，制造层次）
        strands = QPainterPath()
        for sx, sy, ex, ey, c in [
            (hx - 34, hy - 30, hx - 30, hy - 6, 0),
            (hx + 6, hy - 32, hx + 4, hy - 10, 1),
            (hx + 44, hy - 30, hx + 40, hy - 8, 0),
        ]:
            strands.moveTo(sx, sy)
            strands.quadTo((sx + ex) / 2 + c * 6, (sy + ey) / 2, ex, ey)
            strands.lineTo(ex + 5, sy + 8)
            strands.quadTo((sx + ex) / 2 + c * 6 + 2, (sy + ey) / 2 + 8, sx + 3, sy)
            strands.closeSubpath()
        p.setBrush(QBrush(HAIR))
        p.drawPath(strands)

        # 浅色挑染（2-3 缕）
        hi = QPen(HAIR_HI, 5, Qt.SolidLine, Qt.RoundCap)
        p.setPen(hi)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(hx - 30, hy - 88), QPointF(hx - 46, hy - 40))
        p.drawLine(QPointF(hx - 16, hy - 90), QPointF(hx - 22, hy - 46))
        p.drawLine(QPointF(hx + 26, hy - 86), QPointF(hx + 18, hy - 44))

        # 呆毛（一撮翘起的头发）
        ah = QPainterPath()
        ah.moveTo(hx - 2, hy - 90)
        ah.quadTo(hx + 6, hy - 122, hx + 16, hy - 118)
        ah.quadTo(hx + 10, hy - 104, hx + 8, hy - 90)
        ah.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(HAIR))
        p.drawPath(ah)

    # ---------------- 五官 ----------------
    def _draw_face(self, p: QPainter, pose: Pose, hx, hy):
        expr = pose.expression
        look_x, look_y = pose.look

        # 眉毛角度：默认 / angry/sad 变化
        brow_l = 0.0
        brow_r = 0.0
        if expr == "angry":
            brow_l, brow_r = -0.16, -0.16   # 眉尾下压（外低内高 → 用旋转）
        elif expr == "sad":
            brow_l, brow_r = 0.16, 0.16

        # 眼睛参数
        ex1, ey1, ex2, ey2 = hx - 50, hy + 8, hx + 50, hy + 8
        e_rx, e_ry = 20, 23

        def eye_style(side):
            """返回 (类型, 额外) 按表情决定单眼画法。"""
            if expr == "happy":
                return ("happy", None)
            if expr == "wink":
                return ("line", None) if side == 0 else ("normal", None)
            if expr == "love":
                return ("heart", None)
            if expr == "dizz":
                return ("dizz", None)
            if expr == "surprised":
                return ("surprised", None)
            if expr == "sleepy":
                return ("sleepy", None)
            if expr == "tired":
                return ("tired", None)
            if expr == "sad":
                return ("sad", None)
            if expr == "angry":
                return ("angry", None)
            if expr == "cool":
                return ("cool", None)
            if expr == "pout":
                return ("away", (1 if side == 0 else -1) * 0.9)
            if expr == "blush":
                return ("normal", None)
            if expr == "neutral":
                return ("normal", None)
            return ("normal", None)

        for i, (ex, ey) in enumerate([(ex1, ey1), (ex2, ey2)]):
            style, extra = eye_style(i)
            # 眼影（粉调）
            if expr in ("normal", "neutral", "surprised", "happy", "wink", "love", "blush", "cool", "sad"):
                _ell(p, ex, ey - 6, e_rx + 6, 9, EYE_SHADOW)
            # 眉
            brow_tilt = brow_l if i == 0 else brow_r
            bx1, by1 = ex - e_rx * 0.7, ey - e_ry * 0.9
            bx2, by2 = ex + e_rx * 0.7, ey - e_ry * 0.9 + brow_tilt * 40
            pen = QPen(BROW, 4.5, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(bx1, by1 + 2), QPointF(bx2, by2))
            p.drawLine(QPointF(bx1, by1 + 2), QPointF(bx2, by2))

            # 眼睛本体
            if style == "happy":
                # ∩ 型笑眼
                pen = QPen(EYE, 4.5, Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                p.drawArc(QRectF(ex - e_rx, ey - 6, e_rx * 2, e_ry * 1.6),
                          180 * 16, -180 * 16)
                continue
            if style == "line":
                # 眨眼：一条线
                pen = QPen(EYE, 4.5, Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(ex - e_rx, ey + 2), QPointF(ex + e_rx, ey + 2))
                continue
            if style == "heart":
                self._draw_heart(p, ex, ey + 4, 10, EYE)
                continue
            if style == "dizz":
                # 螺旋眼
                pen = QPen(EYE, 3.0)
                p.setPen(pen)
                for k in range(3):
                    r = 4 + k * 5
                    p.drawArc(QRectF(ex - r, ey - r, r * 2, r * 2), k * 90 * 16, 200 * 16)
                continue
            # 常规圆眼（含瞳孔偏移/半闭/不同表情微调）
            open_r = 1.0
            pupil_r = 7.5
            if style == "sleepy":
                open_r, pupil_r = 0.42, 6.0
            elif style == "tired":
                open_r, pupil_r = 0.55, 6.5
            elif style == "sad":
                open_r, pupil_r = 0.7, 5.5
            elif style == "surprised":
                open_r, pupil_r = 1.15, 4.6
            elif style == "angry":
                open_r, pupil_r = 0.8, 5.5
            elif style == "cool":
                open_r, pupil_r = 0.5, 6.5

            ry = e_ry * open_r
            _ell(p, ex, ey, e_rx, ry, EYE)
            # 瞳孔（跟随光标）
            if style == "away":
                lookx = extra
                looky = 0.25
            else:
                lookx, looky = look_x, look_y
            px = ex + lookx * e_rx * 0.42
            py = ey + looky * ry * 0.35
            _ell(p, px, py, pupil_r, pupil_r * 0.95, EYE_HI)
            # 高光
            _ell(p, ex - e_rx * 0.35, ey - ry * 0.28, 5.5, 6.5, EYE_HI)
            # 眨眼遮盖（上眼皮下压）
            if pose.blink > 0 or style in ("sleepy", "tired"):
                cover = 0.0
                if pose.blink > 0:
                    cover = ry * (1.0 - pose.blink)
                else:
                    cover = ry * (0.5 if style == "sleepy" else 0.35)
                _ell(p, ex, ey, e_rx, cover, SKIN)

        # 左脸颊两颗小痣（参考图特征）
        _ell(p, hx - 34, hy + 30, 2.4, 2.4, QColor(120, 84, 70))
        _ell(p, hx - 27, hy + 36, 2.0, 2.0, QColor(120, 84, 70))

        # 鼻
        _ell(p, hx + 2, hy + 24, 2.2, 2.6, SKIN_SH)

        # 嘴
        self._draw_mouth(p, pose, hx, hy)

    def _draw_mouth(self, p: QPainter, pose: Pose, hx, hy):
        expr = pose.expression
        mx, my = hx + 2, hy + 44
        pen = QPen(MOUTH, 3.2, Qt.SolidLine, Qt.RoundCap)
        if expr in ("happy", "love"):
            _arc_mouth(p, mx, my, 12, 9, 200, 140, MOUTH, w=3.4)
        elif expr == "wink":
            _arc_mouth(p, mx, my - 4, 14, 10, 200, 140, MOUTH, w=3.4)
        elif expr == "surprised":
            _ell(p, mx, my + 2, 6, 8, MOUTH, MOUTH_SH, 1.2)
        elif expr == "pout":
            # 傲娇撇嘴：小皱眉（向下弯）
            _arc_mouth(p, mx, my + 2, 10, 7, 180, -150, MOUTH, w=3.2)
        elif expr == "sleepy":
            # 打盹：放松微张的小嘴
            _arc_mouth(p, mx, my + 1, 9, 7, 180, 170, MOUTH, w=3.2)
        elif expr == "tired":
            p.setPen(pen)
            p.drawLine(QPointF(mx - 8, my), QPointF(mx + 8, my))
        elif expr in ("sad", "angry"):
            _arc_mouth(p, mx, my + 6, 12, 9, 180, -150, MOUTH, w=3.2)
        elif expr == "cool":
            # 邪魅一笑：一侧上扬
            p.setPen(pen)
            p.drawLine(QPointF(mx - 10, my + 5), QPointF(mx + 10, my - 3))
        elif expr == "blush":
            # 羞怯：小微笑（轻微下弯）
            _arc_mouth(p, mx, my, 9, 7, 180, 170, MOUTH, w=3.2)
        elif expr == "neutral":
            p.setPen(pen)
            p.drawLine(QPointF(mx - 8, my + 1), QPointF(mx + 8, my + 1))
        else:
            p.setPen(pen)
            p.drawLine(QPointF(mx - 8, my + 1), QPointF(mx + 8, my + 1))
        # bite 时：链条被咬在嘴边
        if pose.action == "bite":
            p.setPen(QPen(CHAIN, 2.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(mx - 6, my + 4), QPointF(mx - 22, my + 14))

    # ---------------- 脸红 / 汗 ----------------
    def _draw_blush(self, p: QPainter, pose: Pose):
        a = int(120 * pose.blush)
        _ell(p, PET_CX - 52, 252, 14, 9, BLUSH, alpha=a)
        _ell(p, PET_CX + 52, 252, 14, 9, BLUSH, alpha=a)

    def _draw_sweat(self, p: QPainter, pose: Pose):
        a = int(180 * pose.sweat)
        n = 3
        for i in range(n):
            ph = pose.phase + i * 2.1
            x = PET_CX - 70 + i * 12 + math.sin(ph) * 3
            y = 180 + i * 14
            _ell(p, x, y, 4, 6, QColor(120, 200, 255, a))

    # ---------------- 道具 ----------------
    def _draw_props(self, p: QPainter, pose: Pose):
        if "sunglasses" in pose.props:
            self._draw_sunglasses(p)
        if "headphones" in pose.props:
            self._draw_headphones(p)
        if "cup" in pose.props:
            self._draw_cup(p, pose)
        if "water" in pose.props:
            self._draw_cup(p, pose, water=True)
        if "crown" in pose.props:
            self._draw_crown(p)

    def _draw_sunglasses(self, p: QPainter):
        # 墨镜
        p.setPen(QPen(QColor(30, 30, 36), 3, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(QBrush(QColor(24, 24, 30)))
        p.drawRoundedRect(QRectF(PET_CX - 74, 218, 40, 26), 8, 8)
        p.drawRoundedRect(QRectF(PET_CX + 34, 218, 40, 26), 8, 8)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(PET_CX - 34, 222), QPointF(PET_CX + 34, 222))
        p.drawLine(QPointF(PET_CX - 72, 224), QPointF(PET_CX - 88, 216))
        p.drawLine(QPointF(PET_CX + 72, 224), QPointF(PET_CX + 88, 216))
        # 镜片高光
        _ell(p, PET_CX - 60, 224, 7, 5, QColor(255, 255, 255, 70))
        _ell(p, PET_CX + 48, 224, 7, 5, QColor(255, 255, 255, 70))

    def _draw_headphones(self, p: QPainter):
        # 头戴式耳机
        pen = QPen(QColor(90, 96, 120), 9, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(PET_CX - 78, 128, 156, 92), 200 * 16, 140 * 16)
        _ell(p, PET_CX - 76, 214, 16, 26, QColor(70, 76, 100))
        _ell(p, PET_CX + 76, 214, 16, 26, QColor(70, 76, 100))

    def _draw_cup(self, p: QPainter, pose: Pose, water=False):
        # 右手举杯（吸管杯）
        cx, cy = PET_CX + 46, 252 + math.sin(pose.phase * 4) * 1.5
        color = QColor(120, 200, 255) if water else QColor(220, 150, 180)
        _rr(p, cx - 13, cy, 26, 30, 6, color)
        _rr(p, cx - 9, cy - 8, 18, 10, 4, QColor(230, 230, 236))
        _ell(p, cx, cy - 14, 5, 7, QColor(70, 170, 90))   # 吸管
        _ell(p, cx, cy + 33, 9, 9, SKIN)                  # 手

    def _draw_crown(self, p: QPainter):
        path = QPainterPath()
        path.moveTo(PET_CX - 26, 130)
        path.lineTo(PET_CX - 26, 108)
        path.lineTo(PET_CX - 14, 122)
        path.lineTo(PET_CX, 104)
        path.lineTo(PET_CX + 14, 122)
        path.lineTo(PET_CX + 26, 108)
        path.lineTo(PET_CX + 26, 130)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(PENDANT))
        p.drawPath(path)
        _ell(p, PET_CX, 118, 2.6, 2.6, QColor(255, 240, 180))

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
                _ell(p, x, y, 3.5, 5.5, QColor(120, 200, 255, int(200 * a)))
            elif kind == "sparkle":
                self._draw_sparkle(p, x, y, 6 * s, QColor(255, 220, 120, int(220 * a)))
            elif kind == "star":
                self._draw_star(p, x, y, 7 * s, QColor(255, 200, 80, int(200 * a)))

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
        margin = 18
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
        by = 12
        # 淡入淡出
        alpha = min(1.0, pose.bubble_t * 3) if pose.bubble_t < 3 else min(1.0, (6.0 - pose.bubble_t) * 0.5)
        alpha = max(0.0, min(1.0, alpha))
        if alpha <= 0:
            return
        # 气泡体
        path = QPainterPath()
        path.addRoundedRect(QRectF(bx, by, bw, text_h + 8), 16, 16)
        # 尾巴
        tail = QPainterPath()
        tail.moveTo(PET_CX - 8, by + text_h + 6)
        tail.quadTo(PET_CX, by + text_h + 26, PET_CX + 10, by + text_h + 6)
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
