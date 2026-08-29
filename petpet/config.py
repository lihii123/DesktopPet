# -*- coding: utf-8 -*-
"""全局配置：可编辑默认值 + 运行时写入 config.json。"""
import json
import os
import sys

# 打包成 exe 后，配置文件放在 exe 同目录；源码运行时放在项目根目录
if getattr(sys, "frozen", False):
    _BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = os.path.join(_BASE, "config.json")

DEFAULT_CONFIG = {
    "pet_name": "阿酷",
    "scale": 0.25,                      # 宠物显示倍率（0.25 = 原尺寸1/4）
    "hotkeys": {
        "toggle_clickthrough": "ctrl+alt+p",   # 点击穿透开关
        "toggle_hide": "ctrl+alt+h",           # 隐藏/显示
        "poke": "ctrl+alt+s",                  # 戳一下（说话/互动）
    },
    "note_text": "",                    # 便签内容（头顶气泡展示）
    "note_enabled": True,
    "reminders": {
        "sedentary_min": 60,            # 久坐提醒（分钟）
        "water_min": 45,                # 喝水提醒（分钟）
        "pomodoro_focus": 25,           # 番茄钟专注（分钟）
        "pomodoro_break": 5,            # 番茄钟休息（分钟）
    },
    "time_greeting": True,              # 时段问候
    "music_nod": True,                  # 音乐节拍点头
    "cpu_sweat": True,                  # CPU 过高擦汗
    "battery_tired": True,              # 低电量犯困
    "rare_enabled": True,               # 稀有动作彩蛋
    "click_through": False,             # 默认不穿透
}


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._deep_merge(DEFAULT_CONFIG, loaded, self.data)
        except Exception:
            pass  # 配置损坏则回退默认

    @staticmethod
    def _deep_merge(base, override, target):
        for k, v in base.items():
            if k in override:
                if isinstance(v, dict) and isinstance(override[k], dict):
                    target[k] = {}
                    Config._deep_merge(v, override[k], target[k])
                else:
                    target[k] = override[k]
            else:
                target[k] = v

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)
