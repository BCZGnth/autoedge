"""autoedge - launch Edge, verify Microsoft login, run human-like Bing searches.

Flow per search:
  1. Generate a query from a topic-based grammar. Searches come in "sessions":
     a few consecutive queries iterate on the same topic (opener + follow-ups),
     then drift to a related or fresh topic, the way a person actually searches.
  2. Search Bing, pick N result pages (1-3) and K links to click (2-7),
     dispersing the K clicks randomly (and out of order) across the N pages.
  3. Scroll every page like a human: attention starts high (careful reading)
     and decays into skimming, with occasional re-reads and early exits.

Run with a search count or a duration:  python autoedge.py 20 | 45m | 1h
"""

import os
import random
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.edge.options import Options

from autoedge.driving.runner import run_search as _run_search
from autoedge.driving.targets.bing_target import BingTarget

PROFILE_DIR = os.path.join(os.environ["LOCALAPPDATA"], "autoedge", "edge-profile")

# ---------------------------------------------------------------------------
# Topic bank. Each topic has a mode (which template set applies), items the
# templates slot into, and related topics the session can drift to.
#   product : items are plural product nouns ("air fryers")
#   howto   : items are bare verb phrases ("grow cherry tomatoes indoors")
#   subject : items are noun phrases facts-templates work on ("black holes")
#   animals : items are (animal, [behaviors]) pairs
# Items are curated so every template in the mode stays grammatical.
# ---------------------------------------------------------------------------

TOPICS = {
    "laptops": {
        "mode": "product",
        "items": ["laptops", "gaming laptops", "chromebooks", "ultrabooks",
                  "laptop cooling pads", "usb-c docking stations"],
        "related": ["office gear", "audio", "tech skills"],
    },
    "audio": {
        "mode": "product",
        "items": ["wireless earbuds", "noise cancelling headphones",
                  "bluetooth speakers", "soundbars", "turntables"],
        "related": ["laptops", "home tech"],
    },
    "kitchen gear": {
        "mode": "product",
        "items": ["air fryers", "espresso machines", "coffee grinders",
                  "cast iron skillets", "stand mixers", "rice cookers",
                  "chef knives"],
        "related": ["cooking", "home tech"],
    },
    "home tech": {
        "mode": "product",
        "items": ["robot vacuums", "smart thermostats", "video doorbells",
                  "mesh wifi systems", "smart plugs", "air purifiers"],
        "related": ["home projects", "kitchen gear"],
    },
    "fitness gear": {
        "mode": "product",
        "items": ["running shoes", "fitness trackers", "adjustable dumbbells",
                  "exercise bikes", "yoga mats", "foam rollers"],
        "related": ["fitness", "outdoor gear"],
    },
    "outdoor gear": {
        "mode": "product",
        "items": ["hiking boots", "camping tents", "sleeping bags",
                  "trekking poles", "insulated water bottles", "headlamps"],
        "related": ["travel", "fitness gear", "photography gear"],
    },
    "office gear": {
        "mode": "product",
        "items": ["standing desks", "ergonomic chairs", "mechanical keyboards",
                  "ultrawide monitors", "webcams", "desk lamps"],
        "related": ["laptops", "tech skills"],
    },
    "cars": {
        "mode": "product",
        "items": ["electric cars", "hybrid suvs", "dash cams",
                  "portable jump starters", "roof cargo boxes"],
        "related": ["travel", "home tech"],
    },
    "photography gear": {
        "mode": "product",
        "items": ["mirrorless cameras", "camera drones", "travel tripods",
                  "camera bags", "prime lenses"],
        "related": ["outdoor gear", "hobbies", "travel"],
    },
    "gardening": {
        "mode": "howto",
        "items": ["grow cherry tomatoes indoors", "keep basil alive",
                  "prune rose bushes", "start a vegetable garden",
                  "care for succulents", "get rid of aphids naturally",
                  "grow an avocado tree from a pit"],
        "related": ["cooking", "home projects"],
    },
    "cooking": {
        "mode": "howto",
        "items": ["make sourdough bread", "make risotto", "make cold brew coffee",
                  "make fresh pasta from scratch", "make a perfect omelette",
                  "make kimchi at home", "sharpen kitchen knives"],
        "related": ["kitchen gear", "gardening", "health habits"],
    },
    "home projects": {
        "mode": "howto",
        "items": ["fix a leaky faucet", "patch a hole in drywall",
                  "unclog a drain without chemicals", "paint a room like a pro",
                  "install a ceiling fan", "soundproof a home office"],
        "related": ["home tech", "gardening"],
    },
    "fitness": {
        "mode": "howto",
        "items": ["train for a 5k", "build muscle at home",
                  "improve flexibility", "fix posture from sitting all day",
                  "start swimming for exercise", "recover after a workout"],
        "related": ["fitness gear", "health habits"],
    },
    "tech skills": {
        "mode": "howto",
        "items": ["speed up a slow laptop", "back up photos automatically",
                  "set up a home media server", "free up disk space on windows",
                  "transfer everything to a new phone", "block spam calls"],
        "related": ["laptops", "office gear"],
    },
    "hobbies": {
        "mode": "howto",
        "items": ["learn conversational spanish", "improve touch typing",
                  "get better at chess", "learn photography basics",
                  "start birdwatching", "practice public speaking"],
        "related": ["photography gear", "travel"],
    },
    "personal finance": {
        "mode": "howto",
        "items": ["start investing with little money", "build an emergency fund",
                  "improve a credit score", "make a monthly budget that sticks",
                  "cut monthly subscription costs", "save for a house deposit"],
        "related": ["tech skills"],
    },
    "pets": {
        "mode": "howto",
        "items": ["train a puppy to sit", "stop a dog pulling on the leash",
                  "introduce a new cat to the house", "clip a dog's nails safely",
                  "set up a freshwater fish tank", "keep an indoor cat active"],
        "related": ["animal facts"],
    },
    "travel": {
        "mode": "howto",
        "items": ["pack light for two weeks", "find cheap flights",
                  "plan a national parks road trip", "avoid jet lag",
                  "travel with a toddler", "choose good travel insurance"],
        "related": ["outdoor gear", "cars", "photography gear"],
    },
    "science": {
        "mode": "subject",
        "items": ["the northern lights", "lightning", "black holes",
                  "ocean tides", "rainbows", "dreams", "deja vu",
                  "volcanic eruptions", "the placebo effect"],
        "related": ["animal facts", "health habits"],
    },
    "health habits": {
        "mode": "subject",
        "items": ["intermittent fasting", "green tea", "the mediterranean diet",
                  "cold showers", "meditation", "standing desks at work",
                  "an afternoon nap", "walking 10000 steps a day"],
        "related": ["fitness", "science", "cooking"],
    },
    "animal facts": {
        "mode": "animals",
        "items": [("cats", ["purr", "knead blankets", "sleep so much"]),
                  ("dogs", ["tilt their heads", "chase their tails", "howl at sirens"]),
                  ("octopuses", ["change color", "squeeze through tiny gaps"]),
                  ("honey bees", ["dance", "make hexagonal honeycomb"]),
                  ("whales", ["sing", "breach out of the water"]),
                  ("migratory birds", ["fly in a v formation", "navigate at night"])],
        "related": ["pets", "science"],
    },
}

# Template sets per mode: (openers, followups). {item} is the session focus,
# {other} a different item from the same topic, {behavior} an animal behavior.
MODES = {
    "product": (
        ["best {item} in 2026",
         "best {item} for {audience}",
         "most reliable {item}",
         "cheapest {item} worth buying",
         "{item} buying guide"],
        ["{item} vs {other}",
         "{item} reviews",
         "how much do {item} cost",
         "best budget {item}",
         "common problems with {item}",
         "are {item} worth it",
         "{item} pros and cons"],
    ),
    "howto": (
        ["how to {item}",
         "easiest way to {item}",
         "best way to {item}",
         "can a beginner {item}"],
        ["how long does it take to {item}",
         "common mistakes when trying to {item}",
         "what do you need to {item}",
         "cheapest way to {item}",
         "step by step guide to {item}",
         "is it hard to {item}"],
    ),
    "subject": (
        ["what causes {item}",
         "science behind {item}",
         "{item} explained",
         "is it worth trying {item}"],
        ["interesting facts about {item}",
         "common myths about {item}",
         "what does research say about {item}",
         "history of {item}",
         "benefits of {item}"],
    ),
    "animals": (
        ["why do {item} {behavior}",
         "interesting facts about {item}"],
        ["how smart are {item}",
         "how long do {item} live",
         "how do {item} communicate",
         "where do {item} live in the wild",
         "why do {item} {behavior}"],
    ),
}

AUDIENCES = ["students", "travel", "small apartments", "beginners",
             "working from home", "seniors", "college", "everyday use"]

# Subject templates that only read well for one kind of subject: you can't
# "try" lightning, and nothing "causes" green tea.
_PHENOMENA = set(TOPICS["science"]["items"])
_PHENOMENA_ONLY = {"what causes {item}"}
_HABITS_ONLY = {"is it worth trying {item}", "benefits of {item}"}


def _fits(template, item):
    if not isinstance(item, str):  # (animal, behaviors) pairs: no filtering
        return True
    if item in _PHENOMENA:
        return template not in _HABITS_ONLY
    return template not in _PHENOMENA_ONLY


class SearchSession:
    """Produces queries the way a person iterates: a short run of related
    queries on one focus item, then a drift to a related or random topic."""

    def __init__(self):
        self.topic = None
        self.remaining = 0

    def _start_session(self):
        if self.topic and random.random() < 0.45:
            choices = TOPICS[self.topic]["related"]
        else:
            choices = [t for t in TOPICS if t != self.topic]
        self.topic = random.choice(choices)
        self.remaining = random.randint(1, 4)
        self.item = random.choice(TOPICS[self.topic]["items"])
        self.opened = False

    def _render(self, template):
        info = TOPICS[self.topic]
        item = self.item
        fields = {}
        if info["mode"] == "animals":
            item, behaviors = item
            fields["behavior"] = random.choice(behaviors)
        fields["item"] = item
        if "{other}" in template:
            fields["other"] = random.choice([i for i in info["items"]
                                             if i != self.item])
        if "{audience}" in template:
            fields["audience"] = random.choice(AUDIENCES)
        return template.format(**fields)

    def next_query(self, used):
        for _ in range(12):
            if self.remaining <= 0:
                self._start_session()
            openers, followups = MODES[TOPICS[self.topic]["mode"]]
            if self.opened and random.random() < 0.25:
                # occasionally shift focus to a sibling item mid-session
                self.item = random.choice(TOPICS[self.topic]["items"])
            pool = followups if self.opened else openers
            template = random.choice([t for t in pool if _fits(t, self.item)])
            query = self._render(template)
            if query not in used:
                self.opened = True
                self.remaining -= 1
                return query
            self.remaining = 0  # exhausted this thread; move on
        # extremely unlikely fallback: accept a repeat rather than spin
        return query


# ---------------------------------------------------------------------------
# Bing plumbing lives in autoedge/driving now (BingTarget + the target-
# agnostic runner), so both this legacy script and any future driver share
# one implementation instead of two.
# ---------------------------------------------------------------------------

def launch_edge():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return webdriver.Edge(options=opts)


# ---------------------------------------------------------------------------
# Run target: a search count ("20") or a duration ("45m", "1h", "1.5h")
# ---------------------------------------------------------------------------

def parse_target(raw):
    raw = raw.strip().lower()
    if raw.isdigit() and int(raw) > 0:
        return ("count", int(raw))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)",
                     raw)
    if m:
        value = float(m.group(1))
        seconds = value * 3600 if m.group(2).startswith("h") else value * 60
        if seconds > 0:
            return ("time", seconds)
    return None


def get_target():
    if len(sys.argv) > 1:
        target = parse_target(sys.argv[1])
        if target:
            return target
        print(f"Didn't understand '{sys.argv[1]}'.")
    while True:
        raw = input("How long should I run? Enter a number of searches "
                    "(e.g. 20) or a duration (e.g. 45m, 1h): ")
        target = parse_target(raw)
        if target:
            return target
        print("Please enter a positive number, or a duration like 30m or 1h.")


def main():
    mode, value = get_target()
    if mode == "time":
        print(f"[*] Running for {value / 60:.0f} minutes.")
    else:
        print(f"[*] Running {value} searches.")

    print("[*] Launching Edge...")
    driver = launch_edge()
    target = BingTarget()
    try:
        target.ensure_ready(driver)
        session = SearchSession()
        used = set()
        deadline = time.monotonic() + value if mode == "time" else None
        i = 0
        while True:
            if mode == "count" and i >= value:
                break
            if deadline and time.monotonic() >= deadline:
                print("[*] Time is up.")
                break
            query = session.next_query(used)
            used.add(query)
            i += 1
            if deadline:
                left = (deadline - time.monotonic()) / 60
                print(f"[search {i} | {left:.0f} min left]")
            else:
                print(f"[{i}/{value}]")
            _run_search(driver, target, query)
            wait = random.uniform(4, 12)
            print(f"  pausing {wait:.0f}s")
            time.sleep(wait)
        print(f"[+] Done - ran {i} searches.")
    finally:
        input("Press Enter to close Edge... ")
        driver.quit()


if __name__ == "__main__":
    main()
