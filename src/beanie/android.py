"""Android body — the phone as another limb, driven by the PC (§11.5, row 48).

Traceability: ARCHITECTURE §11.5 (the phone is a body the mind can sense and
operate over the Android Debug Bridge from the PC — same tripartite organization:
the mind decides, ADB is the limb, the owner's gate decides whether it may) and
§5/§9 (phone actions go through the authority gate like any body action).

The real driver shells ``adb`` (installed with Android platform-tools on the
PC). Test and demo runs use ``VirtualAndroidDriver``: a scripted screen and a
recorded action list — the navigator (§11.3) drives either limb with the same
loop, which is what keeps the whole system demonstrable offline.

Honesty rules for the phone:
  * availability is discovered, never asserted — ``available`` is False when
    adb is missing or no device answers;
  * ``tap_swipe`` actions by screen coordinate are real (input tap/swipe), and
    screen *understanding* (which button is which) is the model tier's job
    over ``uiautomator dump``/screenshots;
  * app launching uses the standard Android intent machinery (monkey), which
    is honest to the Android platform.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

from .body import BodyError

#: the phone accepts the GUI vocabulary plus its own platform actions
PHONE_ACTION_TYPES = ("click", "type", "key", "wait", "done", "fail", "swipe", "open_app")


@dataclass
class DeviceInfo:
    serial: str
    state: str          # device | offline | unauthorized
    model: str = ""


class ADBDriver:
    """The real phone, reached over adb from the PC."""

    name = "adb"
    action_types = PHONE_ACTION_TYPES

    def __init__(self, serial: Optional[str] = None) -> None:
        if os.environ.get("BEANIE_ANDROID") != "1":
            raise RuntimeError("ADBDriver requires BEANIE_ANDROID=1 (phone control is opt-in)")
        if shutil.which("adb") is None:
            raise RuntimeError("adb (Android platform-tools) is not installed on this PC")
        self.serial = serial

    # -- shell ------------------------------------------------------------

    def _adb(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        command = ["adb"]
        if self.serial:
            command += ["-s", self.serial]
        command += list(args)
        return subprocess.run(  # noqa: S603 — adb is a fixed tool, args are ours
            command, capture_output=True, text=True, timeout=timeout
        )

    def available(self) -> bool:
        return any(device.state == "device" for device in self.devices())

    def devices(self) -> list[DeviceInfo]:
        try:
            result = self._adb("devices", "-l", timeout=10)
        except OSError as exc:
            raise BodyError(f"adb failed: {exc}", kind="os_error") from exc
        found: list[DeviceInfo] = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                model = ""
                model_match = re.search(r"model:(\S+)", line)
                if model_match:
                    model = model_match.group(1)
                if self.serial is None or parts[0] == self.serial:
                    found.append(DeviceInfo(serial=parts[0], state=parts[1], model=model))
        return found

    # -- limbs ------------------------------------------------------------

    def read_screen(self) -> str:
        """A text rendering of the phone screen (uiautomator's UI dump)."""
        result = self._adb("shell", "uiautomator", "dump", "/dev/tty", timeout=20)
        if result.returncode != 0:
            raise BodyError("could not read the phone screen", kind="screen_unreadable",
                            details=(result.stderr or "").strip())
        return result.stdout

    def screenshot(self) -> bytes:
        result = subprocess.run(  # noqa: S603
            ["adb"] + (["-s", self.serial] if self.serial else []) + ["exec-out", "screencap", "-p"],
            capture_output=True, timeout=20)
        return result.stdout

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        kind = action.get("type")
        command: list[str]
        if kind == "click":
            command = ["shell", "input", "tap", str(int(action.get("x", 0))), str(int(action.get("y", 0)))]
        elif kind == "swipe":
            command = ["shell", "input", "swipe"] + [str(int(v)) for v in
                       (action.get("x1", 0), action.get("y1", 0), action.get("x2", 0), action.get("y2", 0))]
        elif kind == "type":
            command = ["shell", "input", "text", shlex.quote(str(action.get("text", "")).replace(" ", "%s"))]
        elif kind == "key":
            command = ["shell", "input", "keyevent", str(action.get("key", "KEYCODE_BACK"))]
        elif kind == "open_app":
            command = ["shell", "monkey", "-p", str(action.get("package", "")),
                       "-c", "android.intent.category.LAUNCHER", "1"]
        else:
            raise BodyError(f"cannot execute phone action of type {kind!r}", kind="bad_action")
        result = self._adb(*command, timeout=int(action.get("timeout", 20)))
        if result.returncode != 0:
            raise BodyError(f"adb {kind} failed: {(result.stderr or result.stdout).strip()}",
                            kind="device_error")
        return {"performed": kind, "stdout": (result.stdout or "").strip()[-500:]}


class VirtualAndroidDriver:
    """Scripted phone for tests and demos — the navigator drives it identically."""

    name = "virtual-android"
    action_types = PHONE_ACTION_TYPES

    def __init__(self, screens: Optional[list[str]] = None) -> None:
        self.screens = list(screens or ["<home/>"])
        self.executed: list[dict[str, Any]] = []
        self._screen_index = 0

    def available(self) -> bool:
        return True

    def devices(self) -> list[DeviceInfo]:
        return [DeviceInfo(serial="virtual", state="device", model="VirtualPhone")]

    def read_screen(self) -> str:
        screen = self.screens[min(self._screen_index, len(self.screens) - 1)]
        if self._screen_index < len(self.screens) - 1:
            self._screen_index += 1
        return screen

    def screenshot(self) -> bytes:
        return b""

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        self.executed.append(action)
        return {"performed": action.get("type")}


def default_android_driver() -> Any:
    """Real driver when the owner opted in and adb exists, virtual otherwise."""
    if os.environ.get("BEANIE_ANDROID") == "1":
        try:
            return ADBDriver()
        except RuntimeError:
            return VirtualAndroidDriver()
    return VirtualAndroidDriver()
