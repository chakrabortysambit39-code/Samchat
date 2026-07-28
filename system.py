"""
system.py
System info and control: CPU/RAM/battery/disk stats, launching
applications, and (guarded) shutdown/restart/lock.
"""
import os
import subprocess
import sys

import psutil

from utils import get_logger

log = get_logger("system")


def get_status() -> str:
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.expanduser("~"))
    lines = [
        f"CPU usage: {cpu}%",
        f"Memory: {mem.percent}% used ({mem.used // (1024**2)} MB / {mem.total // (1024**2)} MB)",
        f"Disk: {disk.percent}% used ({disk.used // (1024**3)} GB / {disk.total // (1024**3)} GB)",
    ]
    try:
        battery = psutil.sensors_battery()
        if battery:
            state = "charging" if battery.power_plugged else "on battery"
            lines.append(f"Battery: {battery.percent}% ({state})")
    except (AttributeError, NotImplementedError):
        pass
    return "\n".join(lines)


def open_application(app_name: str) -> str:
    """Best-effort cross-platform app launcher by executable/app name."""
    app_name = app_name.strip()
    try:
        if sys.platform.startswith("win"):
            os.startfile(app_name)  # noqa: F821 (Windows only)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-a", app_name], check=True)
        else:
            subprocess.run([app_name], check=True)
        return f"Opening {app_name}."
    except Exception as e:
        log.warning("open_application failed for %s: %s", app_name, e)
        return f"I couldn't find or launch '{app_name}' on this machine."


def _confirm_or_message(action_name: str, confirm: bool) -> str:
    return f"Say it again with confirmation to actually {action_name} this machine."


def shutdown(confirm: bool = False) -> str:
    if not confirm:
        return _confirm_or_message("shut down", confirm)
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["shutdown", "/s", "/t", "5"], check=True)
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'], check=True)
        else:
            subprocess.run(["shutdown", "-h", "now"], check=True)
        return "Shutting down."
    except Exception as e:
        log.warning("shutdown failed: %s", e)
        return "I couldn't shut down the machine (probably a permissions issue)."


def restart(confirm: bool = False) -> str:
    if not confirm:
        return _confirm_or_message("restart", confirm)
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["shutdown", "/r", "/t", "5"], check=True)
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", 'tell app "System Events" to restart'], check=True)
        else:
            subprocess.run(["reboot"], check=True)
        return "Restarting."
    except Exception as e:
        log.warning("restart failed: %s", e)
        return "I couldn't restart the machine (probably a permissions issue)."


def lock_screen() -> str:
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
        elif sys.platform == "darwin":
            subprocess.run(["pmset", "displaysleepnow"], check=True)
        else:
            subprocess.run(["xdg-screensaver", "lock"], check=True)
        return "Locking the screen."
    except Exception as e:
        log.warning("lock_screen failed: %s", e)
        return "I couldn't lock the screen on this machine."
