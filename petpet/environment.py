# -*- coding: utf-8 -*-
"""环境感知：屏幕/任务栏、活动窗口、CPU、电量、音乐。

所有 Windows 专属调用都做 try/except 兜底，任一能力缺失时返回安全默认值，
保证在开发机（无 Windows API）上也能跑逻辑层。
"""
import time

try:
    import psutil
except Exception:
    psutil = None

_IS_WIN = False
try:
    import win32api
    import win32gui
    import win32con
    _IS_WIN = True
except Exception:
    win32api = win32gui = win32con = None

# 常见音乐播放器进程名（用于节拍点头检测）
MUSIC_PROCESSES = {
    "spotify.exe", "cloudmusic.exe", "qqmusic.exe", "kugou.exe",
    "itunes.exe", "foobar2000.exe", "music.ui.exe", "bilibili.exe",
    "douyin.exe", "kwmusic.exe", "网易云音乐.exe", "酷狗音乐.exe",
}


def is_windows():
    return _IS_WIN


def get_screen_rect():
    """返回 (x, y, w, h) 工作区（不含任务栏），失败返回 1920x1080 默认。"""
    if _IS_WIN:
        try:
            return win32api.SystemParametersInfo(win32con.SPI_GETWORKAREA)
        except Exception:
            pass
    return (0, 0, 1920, 1040)


def get_floor_y():
    """宠物站立的地面 y（工作区底部）。"""
    _, _, _, h = get_screen_rect()
    return h


def get_screen_width():
    _, _, w, _ = get_screen_rect()
    return w


def get_active_window_rect():
    """返回前台窗口的 (left, top, right, bottom)；无/异常返回 None。"""
    if not _IS_WIN:
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        # 跳过自己的宠物窗口（名称匹配）
        try:
            name = win32gui.GetWindowText(hwnd)
        except Exception:
            name = ""
        if not name or name.startswith("阿酷"):
            return None
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right - left < 200 or bottom - top < 120:
            return None
        return (left, top, right, bottom)
    except Exception:
        return None


def get_foreground_process_name():
    if not _IS_WIN:
        return ""
    try:
        hwnd = win32gui.GetForegroundWindow()
        pid = win32api.GetWindowThreadProcessId(hwnd)[1]
        proc = psutil.Process(pid) if psutil else None
        if proc:
            return proc.name().lower()
    except Exception:
        pass
    return ""


def is_music_playing():
    """启发式判断：前台进程是否为常见播放器，或系统有活跃音频会话。"""
    if get_foreground_process_name() in MUSIC_PROCESSES:
        return True
    # 尝试用 pycaw 读取活跃音频会话（可选依赖，未装则忽略）
    try:
        from comtypes import CLSCTX_ALL  # noqa
        from pycaw.pycaw import AudioUtilities  # noqa
        sessions = AudioUtilities.GetAllSessions()
        for s in sessions:
            if s.Process and s.Process.name().lower() in MUSIC_PROCESSES and s.State == 1:
                return True
    except Exception:
        pass
    return False


class CpuMonitor:
    """CPU 占用监控：连续高则触发擦汗。"""

    def __init__(self, high=75.0, hold_seconds=2.0):
        self.high = high
        self.hold_seconds = hold_seconds
        self._samples = []
        self._last_sample = 0.0
        self.hot = False
        self.hot_since = 0.0

    def sample(self):
        if psutil is None:
            return False
        now = time.monotonic()
        if now - self._last_sample < 0.8:
            return self.hot
        self._last_sample = now
        try:
            v = psutil.cpu_percent(interval=None)
        except Exception:
            v = 0.0
        self._samples.append(v)
        if len(self._samples) > 8:
            self._samples.pop(0)
        avg = sum(self._samples) / len(self._samples) if self._samples else 0
        if avg >= self.high:
            if not self.hot:
                self.hot = True
                self.hot_since = now
        else:
            if self.hot and now - self.hot_since > self.hold_seconds:
                self.hot = False
        return self.hot


class BatteryMonitor:
    """电量监控：低电量犯困。"""

    def __init__(self, low=20):
        self.low = low
        self.percent = 100
        self.charging = False
        self.last_check = 0.0

    def sample(self):
        if psutil is None:
            return
        now = time.monotonic()
        if now - self.last_check < 10.0:
            return
        self.last_check = now
        try:
            b = psutil.sensors_battery()
            if b is not None:
                self.percent = int(b.percent)
                self.charging = bool(b.power_plugged)
        except Exception:
            pass

    @property
    def low_battery(self):
        return self.percent <= self.low and not self.charging
