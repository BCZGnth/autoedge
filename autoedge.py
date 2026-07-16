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
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROFILE_DIR = os.path.join(os.environ["LOCALAPPDATA"], "autoedge", "edge-profile")
BING = "https://www.bing.com/"

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
# Human behavior primitives
# ---------------------------------------------------------------------------

def pause(lo, hi):
    time.sleep(random.uniform(lo, hi))


def human_type(element, text):
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(0.05, 0.22))
        if random.random() < 0.04:  # occasional hesitation mid-thought
            time.sleep(random.uniform(0.4, 1.1))


def human_scroll(driver):
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


# ---------------------------------------------------------------------------
# Bing plumbing
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


def dismiss_cookie_banner(driver):
    try:
        driver.find_element(By.ID, "bnp_btn_accept").click()
        pause(0.5, 1.0)
    except (NoSuchElementException, ElementClickInterceptedException):
        pass


def is_signed_in(driver):
    """On bing.com, #id_n holds the display name when a Microsoft account is
    signed in; the #id_a anchor reads 'Sign in' when it is not."""
    try:
        name = driver.find_element(By.ID, "id_n")
        if name.get_attribute("textContent").strip():
            return True
    except NoSuchElementException:
        pass
    try:
        return "sign in" not in driver.find_element(By.ID, "id_a").text.strip().lower()
    except NoSuchElementException:
        return False


def ensure_signed_in(driver):
    driver.get(BING)
    dismiss_cookie_banner(driver)
    pause(1.0, 2.0)
    if is_signed_in(driver):
        print("[+] Microsoft account is signed in.")
        return
    print("[!] Not signed in. Please sign in to your Microsoft account in the")
    print("    Edge window that just opened (click the profile icon, top right).")
    input("    Press Enter here once you are signed in... ")
    driver.get(BING)
    pause(1.0, 2.0)
    if not is_signed_in(driver):
        print("[!] Still can't confirm the login - continuing anyway.")
    else:
        print("[+] Login confirmed.")


def submit_search(driver, query):
    driver.get(BING)
    dismiss_cookie_banner(driver)
    box = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "sb_form_q"))
    )
    box.click()
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(Keys.DELETE)
    human_type(box, query)
    pause(0.3, 0.9)
    box.send_keys(Keys.RETURN)
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "li.b_algo"))
    )


def result_links(driver):
    """Clickable organic-result anchors on the current results page."""
    anchors = driver.find_elements(By.CSS_SELECTOR, "li.b_algo h2 a")
    return [a for a in anchors if a.get_attribute("href")]


def goto_next_page(driver):
    try:
        nxt = driver.find_element(By.CSS_SELECTOR, "a.sb_pagN")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'})", nxt)
        pause(0.5, 1.2)
        nxt.click()
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.b_algo"))
        )
        return True
    except (NoSuchElementException, TimeoutException,
            ElementClickInterceptedException, StaleElementReferenceException):
        return False


def visit_result(driver, index):
    """Click the index-th organic result, read it like a human, come back."""
    links = result_links(driver)
    if index >= len(links):
        return
    link = links[index]
    serp = driver.current_url
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'})", link)
        pause(0.6, 1.5)
        title = link.text[:60]
        link.click()
        print(f"      -> reading: {title}")
        pause(2.0, 4.0)  # page settle / first impression
        human_scroll(driver)
    except WebDriverException as exc:
        print(f"      -> couldn't read that one ({type(exc).__name__}), moving on")
    finally:
        # get back to the results page no matter how the site behaved
        for _ in range(3):
            if "bing.com/search" in driver.current_url:
                break
            driver.back()
            pause(1.0, 2.0)
        if "bing.com/search" not in driver.current_url:
            driver.get(serp)
            pause(1.0, 2.0)


def disperse(total_clicks, num_pages):
    """Spread total_clicks across num_pages, every page getting >= 0."""
    counts = [0] * num_pages
    for _ in range(total_clicks):
        counts[random.randrange(num_pages)] += 1
    return counts


def run_search(driver, query):
    num_pages = random.randint(1, 3)
    num_clicks = random.randint(2, 7)
    plan = disperse(num_clicks, num_pages)
    print(f'  searching: "{query}"')
    print(f"  plan: {num_pages} page(s), {num_clicks} click(s) dispersed as {plan}")

    submit_search(driver, query)

    for page, clicks in enumerate(plan, start=1):
        pause(1.0, 2.5)
        human_scroll(driver)  # skim the results page itself

        available = len(result_links(driver))
        if available == 0:
            break
        picks = random.sample(range(min(available, 10)), min(clicks, available, 10))
        random.shuffle(picks)  # click out of order
        for index in picks:
            visit_result(driver, index)
            pause(1.5, 3.5)

        if page < num_pages:
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight)")
            pause(0.8, 1.6)
            if not goto_next_page(driver):
                print("  no further result pages; stopping this search early")
                break


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
    try:
        ensure_signed_in(driver)
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
            run_search(driver, query)
            wait = random.uniform(4, 12)
            print(f"  pausing {wait:.0f}s")
            time.sleep(wait)
        print(f"[+] Done - ran {i} searches.")
    finally:
        input("Press Enter to close Edge... ")
        driver.quit()


if __name__ == "__main__":
    main()
