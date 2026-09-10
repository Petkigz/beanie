"""The Android body (§11.5, row 48): the phone as a limb driven by the PC.

The virtual driver demonstrates the full navigator integration; the ADB driver
is verified for its honest opt-in and for availability discovery that never
claims a phone exists when none answers.
"""

from __future__ import annotations

import pytest

from beanie.android import ADBDriver, VirtualAndroidDriver, default_android_driver
from beanie.automation import Navigator
from beanie.substrate import StubSubstrate


def test_adb_requires_opt_in(monkeypatch):
    monkeypatch.delenv("BEANIE_ANDROID", raising=False)
    with pytest.raises(RuntimeError):
        ADBDriver()


def test_adb_missing_binary_is_loud(monkeypatch):
    monkeypatch.setenv("BEANIE_ANDROID", "1")
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="adb"):
        ADBDriver()


def test_default_falls_back_to_virtual_without_an_attempt(monkeypatch):
    monkeypatch.delenv("BEANIE_ANDROID", raising=False)
    driver = default_android_driver()
    assert isinstance(driver, VirtualAndroidDriver) and driver.available()


def test_navigator_drives_the_phone_like_any_other_body():
    phone = VirtualAndroidDriver(screens=["<home><app>WhatsApp</app></home>", "<chat/>"])
    substrate = StubSubstrate(scripted_gui_actions=[
        {"type": "open_app", "package": "com.whatsapp", "reason": "open the target app"},
        {"type": "done", "reason": "whatsapp is open"},
    ])
    report = Navigator(phone, substrate).run("open whatsapp on my phone")
    assert report.outcome == "completed"
    assert phone.executed[0]["type"] == "open_app"
    assert phone.executed[0]["package"] == "com.whatsapp"


def test_device_listing_reports_state_honestly():
    phone = VirtualAndroidDriver()
    devices = phone.devices()
    assert devices[0].state == "device"
    assert phone.available() is True
