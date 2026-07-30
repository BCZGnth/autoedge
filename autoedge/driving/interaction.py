"""Human-like interaction primitives shared by every SearchTarget: typing,
pausing, and reading (scrolling) a page. Target-agnostic -- these only ever
touch a Selenium `driver`, never a target's own page structure.

Currently simple hand-written approximations, moved here unchanged from the
original single-file script. A future pass wraps in the vendored HumanCursor
/ HumanTyping libraries for more realistic mouse paths and keystroke timing;
`human_scroll`'s attention-decay model stays as-is when that happens.
"""

from __future__ import annotations

import random
import time


def pause(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def human_type(element, text: str) -> None:
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(0.05, 0.22))
        if random.random() < 0.04:  # occasional hesitation mid-thought
            time.sleep(random.uniform(0.4, 1.1))


def human_scroll(driver) -> None:
    """Scroll a page the way a person with a finite attention span reads it.

    Attention starts high (small scrolls, long dwells = careful reading) and
    decays multiplicatively. As it drops the scrolls get bigger and dwells
    shorter (skimming). ~12% of steps scroll back up to re-read, and once
    attention falls below a threshold the reader gives up wherever they are.
    """
    attention = random.uniform(0.75, 1.0)
    give_up_at = random.uniform(0.12, 0.25)

    while attention > give_up_at:
        height = driver.execute_script("return document.body.scrollHeight")
        pos = driver.execute_script("return window.pageYOffset")
        viewport = driver.execute_script("return window.innerHeight")
        if pos + viewport >= height - 50:
            break

        if random.random() < 0.12:
            step = -random.randint(150, 450)   # re-read something above
        else:
            skim = 1.8 - attention              # low attention -> bigger jumps
            step = int(random.randint(220, 480) * skim)

        # glide in small increments rather than teleporting
        remaining = step
        while abs(remaining) > 0:
            inc = max(min(remaining, random.randint(40, 90)), -random.randint(40, 90))
            driver.execute_script("window.scrollBy(0, arguments[0])", inc)
            remaining -= inc
            time.sleep(random.uniform(0.02, 0.06))

        # dwell: reading time scales with how engaged we still are
        time.sleep(random.uniform(0.6, 2.8) * (0.4 + attention))
        attention *= random.uniform(0.86, 0.97)

    pause(0.3, 1.2)
