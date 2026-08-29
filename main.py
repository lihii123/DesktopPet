# -*- coding: utf-8 -*-
"""阿酷 —— 潮酷少年桌面宠物 启动入口。

用法（Windows 开发调试）：
    pip install -r requirements.txt
    python main.py

打包 .exe：
    双击 build.bat 即可（详见 README.md）。
"""
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("阿酷")
    app.setQuitOnLastWindowClosed(False)

    # 让 Windows 任务栏正确显示托盘图标
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "aku.desktoppet")
        except Exception:
            pass

    from petpet.config import Config
    from petpet.pet import Pet
    from petpet.behaviors import Behaviors
    from petpet.reminders import Reminders
    from petpet.window import PetWindow
    from petpet.tray import Tray
    from petpet.hotkeys import Hotkeys

    cfg = Config()
    screen = app.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0

    pet = Pet(cfg, dpr=dpr)
    behaviors = Behaviors(pet, cfg)
    reminders = Reminders(cfg, pet.say, behaviors.flash_action)

    win = PetWindow(pet, behaviors, reminders, cfg, dpr)
    tray = Tray(win, pet, reminders, cfg, app)

    # 定时刷新托盘上的番茄钟状态
    tooltip_timer = QTimer()
    tooltip_timer.timeout.connect(tray.update_pomodoro_tooltip)
    tooltip_timer.start(1000)

    try:
        hotkeys = Hotkeys(win, pet)
    except Exception:
        hotkeys = None

    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
