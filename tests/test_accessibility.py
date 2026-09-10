"""Accessibility eyes (§11.3, row 47): the desktop UI tree is real, named, coordinate text.

Buttons have names and bounding boxes on every desktop platform — the vision
model is NOT the only way to see a screen. The accessibility driver reads that
tree, formats it as bounded screen text for the navigator, and resolves a
*named* target ("Login") to the coordinates of the real element. Unavailable
platforms/deps are answers, not crashes.
"""

from __future__ import annotations

import pytest

from beanie.accessibility import (
    ATGUIDriver,
    PlatformATDriver,
    ScriptBackend,
    UIElement,
)

ELEMENTS = [
    UIElement(name="File", role="menu", x=10, y=4, width=60, height=20),
    UIElement(name="Username", role="edit", x=100, y=200, width=200, height=28),
    UIElement(name="Password", role="edit", x=100, y=240, width=200, height=28),
    UIElement(name="Login", role="button", x=140, y=300, width=120, height=36),
    UIElement(name="Forgot password?", role="link", x=140, y=346, width=140, height=18),
]


def test_screen_is_bounded_named_text_for_the_navigator():
    driver = PlatformATDriver(backend=ScriptBackend(ELEMENTS))
    assert driver.available is True
    screen = driver.read_screen()
    assert "button 'Login' at (200, 318)" in screen      # center of the real bounds
    assert "edit 'Username'" in screen
    assert len(screen.splitlines()) <= 80                 # bounded: the loop never drowns


def test_find_resolves_names_case_insensitively_and_fuzzily():
    driver = PlatformATDriver(backend=ScriptBackend(ELEMENTS))
    hit = driver.find("login")
    assert hit is not None and hit.role == "button"
    assert hit.center == (200, 318)
    near = driver.find("logn")                             # one-letter typo still lands
    assert near is not None and near.name == "Login"
    assert driver.find("nothing-like-this") is None        # honest miss, no guess


def test_no_backend_is_an_answer_not_a_crash():
    driver = PlatformATDriver(backend=None, unavailable_reason="no atspi on this platform")
    assert driver.available is False
    assert "atspi" in driver.unavailable_reason
    with pytest.raises(Exception) as error:
        driver.read_screen()
    assert "not available" in str(error.value).lower()


class _Motion:
    """Records pointer motion like pyautogui would perform it."""

    def __init__(self):
        self.clicks: list[tuple[int, int]] = []
        self.typed: list[str] = []
        self.keys: list[str] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def typewrite(self, text: str, interval: float = 0.0) -> None:
        self.typed.append(text)

    def press(self, key: str) -> None:
        self.keys.append(key)


def test_click_by_target_name_lands_on_the_real_element():
    backend = ScriptBackend(ELEMENTS)
    motion = _Motion()
    driver = ATGUIDriver(backend=backend, motion=motion)
    result = driver.execute({"type": "click", "target": "Login"})
    assert motion.clicks == [(200, 318)]
    assert result["at"] == [200, 318]
    result = driver.execute({"type": "type", "target": "Username", "text": "kigz"})
    assert motion.clicks[-1] == (200, 214)      # focuses the field first, then types
    assert motion.typed == ["kigz"]
    driver.execute({"type": "key", "key": "ENTER"})
    assert motion.keys == ["ENTER"]


def test_click_on_a_name_that_is_not_there_is_an_honest_failure():
    from beanie.body import BodyError

    motion = _Motion()
    driver = ATGUIDriver(backend=ScriptBackend(ELEMENTS), motion=motion)
    with pytest.raises(BodyError) as error:
        driver.execute({"type": "click", "target": "NoSuchButton"})
    assert error.value.kind == "target_not_found"
    assert motion.clicks == []                       # nothing clicked blindly
