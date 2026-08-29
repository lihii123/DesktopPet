# -*- coding: utf-8 -*-
"""系统托盘：菜单、图标、隐藏/显示、点击穿透开关、提醒设置、番茄钟控制。"""
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QIcon, QImage, QPainter, QColor, QPixmap, QFont
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QInputDialog, QMessageBox

from . import dialogue
from .renderer import PetRenderer, Pose, CANVAS_W, CANVAS_H
from . import __version__


def make_tray_icon():
    """用渲染器画一张「头部特写」作为托盘图标。"""
    img = QImage(64, 64, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    r = PetRenderer()
    # 画整只（放大后裁剪头部），用大画布提高清晰度
    big = QImage(int(CANVAS_W * 2), int(CANVAS_H * 2), QImage.Format_ARGB32)
    big.fill(QColor(0, 0, 0, 0))
    bp = QPainter(big)
    bp.setRenderHint(QPainter.Antialiasing, True)
    r.render(bp, Pose(expression="cool", action="idle", props={"sunglasses"}), 2.0)
    bp.end()
    # 裁剪头部区域：本地 (150,214) 半径约 100
    src = big.copy(int((150 - 100) * 2), int((150 - 92) * 2),
                   int(200 * 2), int(196 * 2))
    src = src.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    # 居中合成
    pm = QPixmap.fromImage(src)
    p.drawPixmap((64 - pm.width()) // 2, (64 - pm.height()) // 2, pm)
    p.end()
    return QIcon(QPixmap.fromImage(img))


class Tray:
    def __init__(self, window, pet, reminders, cfg, app):
        self.window = window
        self.pet = pet
        self.reminders = reminders
        self.cfg = cfg
        self.app = app

        self.tray = QSystemTrayIcon(make_tray_icon(), app)
        self.tray.setToolTip("阿酷 · 桌面宠物")
        self.menu = QMenu()

        self.act_toggle = QAction("隐藏到托盘", self.menu)
        self.act_toggle.triggered.connect(self._toggle_visible)
        self.menu.addAction(self.act_toggle)

        self.menu.addAction("戳一下", self._poke)
        self.menu.addAction("说句话", self._chat)

        self.menu.addSeparator()

        self.act_ct = QAction("点击穿透（不挡鼠标）", self.menu, checkable=True)
        self.act_ct.setChecked(self.window.click_through)
        self.act_ct.triggered.connect(self._toggle_ct)
        self.menu.addAction(self.act_ct)

        self.menu.addSeparator()

        self.menu.addAction("设置便签…", self._edit_note)

        self._build_reminder_menu()

        self.menu.addSeparator()
        self.menu.addAction("关于", self._about)
        self.menu.addAction("退出", self._quit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _build_reminder_menu(self):
        sub = self.menu.addMenu("提醒设置")
        r = self.cfg.get("reminders", {})
        self.act_sed = QAction("久坐提醒", sub, checkable=True)
        self.act_sed.setChecked(int(r.get("sedentary_min", 0)) > 0)
        self.act_sed.triggered.connect(self._toggle_sedentary)
        sub.addAction(self.act_sed)
        self.act_water = QAction("喝水提醒", sub, checkable=True)
        self.act_water.setChecked(int(r.get("water_min", 0)) > 0)
        self.act_water.triggered.connect(self._toggle_water)
        sub.addAction(self.act_water)

        sub.addSeparator()
        psub = sub.addMenu("番茄钟")
        self.act_pomo_start = QAction("开始（25 分钟专注）", psub)
        self.act_pomo_start.triggered.connect(self.reminders.start_pomodoro)
        psub.addAction(self.act_pomo_start)
        self.act_pomo_pause = QAction("暂停", psub)
        self.act_pomo_pause.triggered.connect(self.reminders.pause_pomodoro)
        psub.addAction(self.act_pomo_pause)
        self.act_pomo_resume = QAction("继续", psub)
        self.act_pomo_resume.triggered.connect(self.reminders.resume_pomodoro)
        psub.addAction(self.act_pomo_resume)
        self.act_pomo_reset = QAction("重置", psub)
        self.act_pomo_reset.triggered.connect(self.reminders.reset_pomodoro)
        psub.addAction(self.act_pomo_reset)

    # ---------------- 行为 ----------------
    def _toggle_visible(self):
        if self.window.isVisible():
            self.window.hide_pet()
            self.act_toggle.setText("显示宠物")
        else:
            self.window.show_pet()
            self.act_toggle.setText("隐藏到托盘")

    def _poke(self):
        self.pet.poke()

    def _chat(self):
        self.pet.say(dialogue.pick_line("idle"), 3.5)

    def _toggle_ct(self, checked):
        self.window.set_click_through(checked)
        self.pet.say("开了穿透，我不挡你干活。", 2.5)

    def _edit_note(self):
        cur = self.cfg.get("note_text", "")
        text, ok = QInputDialog.getMultiLineText(self.window, "设置便签",
                                                 "输入便签内容（会出现在宠物头顶气泡里）：", cur)
        if ok:
            self.cfg.data["note_text"] = text.strip()
            self.cfg.save()
            self.pet.say("便签更新好啦。" if text.strip() else "便签已清空。", 2.8)

    def _toggle_sedentary(self, checked):
        r = self.cfg.get("reminders", {})
        r["sedentary_min"] = 60 if checked else 0
        self.cfg.save()
        self.pet.say("久坐提醒已开启，我会盯住你。" if checked else "久坐提醒已关闭。", 2.8)

    def _toggle_water(self, checked):
        r = self.cfg.get("reminders", {})
        r["water_min"] = 45 if checked else 0
        self.cfg.save()
        self.pet.say("喝水提醒已开启。" if checked else "喝水提醒已关闭。", 2.8)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_visible()

    def _about(self):
        QMessageBox.about(self.window, "阿酷 桌面宠物",
                          f"潮酷少年桌面宠物 v{__version__}\n\n"
                          "摸一摸会害羞，拖起来会挣扎，\n"
                          "按 Ctrl+Alt+P 开启点击穿透，Ctrl+Alt+H 隐藏到托盘。")

    def _quit(self):
        self.cfg.save()
        self.tray.hide()
        self.app.quit()

    def update_pomodoro_tooltip(self):
        self.tray.setToolTip("阿酷 · 桌面宠物\n" + self.reminders.pomodoro_label())
