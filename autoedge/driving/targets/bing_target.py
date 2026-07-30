"""Opt-in SearchTarget that talks to real bing.com. Never selected by
default -- driving a live search engine is something a caller must ask for
explicitly, unlike MockTarget which is safe to run unattended.
"""

from __future__ import annotations

from typing import Any

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..interaction import human_type, pause
from .base import SearchTarget

BING = "https://www.bing.com/"


class BingTarget(SearchTarget):
    name = "bing"

    def _dismiss_cookie_banner(self, driver: Any) -> None:
        try:
            driver.find_element(By.ID, "bnp_btn_accept").click()
            pause(0.5, 1.0)
        except (NoSuchElementException, ElementClickInterceptedException):
            pass

    def _is_signed_in(self, driver: Any) -> bool:
        """On bing.com, #id_n holds the display name when a Microsoft
        account is signed in; the #id_a anchor reads 'Sign in' when not."""
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

    def ensure_ready(self, driver: Any) -> None:
        driver.get(BING)
        self._dismiss_cookie_banner(driver)
        pause(1.0, 2.0)
        if self._is_signed_in(driver):
            print("[+] Microsoft account is signed in.")
            return
        print("[!] Not signed in. Please sign in to your Microsoft account in the")
        print("    Edge window that just opened (click the profile icon, top right).")
        input("    Press Enter here once you are signed in... ")
        driver.get(BING)
        pause(1.0, 2.0)
        if not self._is_signed_in(driver):
            print("[!] Still can't confirm the login - continuing anyway.")
        else:
            print("[+] Login confirmed.")

    def submit_search(self, driver: Any, query: str) -> None:
        driver.get(BING)
        self._dismiss_cookie_banner(driver)
        box = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "sb_form_q")))
        box.click()
        box.send_keys(Keys.CONTROL, "a")
        box.send_keys(Keys.DELETE)
        human_type(box, query)
        pause(0.3, 0.9)
        box.send_keys(Keys.RETURN)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.b_algo")))

    def result_links(self, driver: Any) -> list:
        anchors = driver.find_elements(By.CSS_SELECTOR, "li.b_algo h2 a")
        return [a for a in anchors if a.get_attribute("href")]

    def goto_next_page(self, driver: Any) -> bool:
        try:
            nxt = driver.find_element(By.CSS_SELECTOR, "a.sb_pagN")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'})", nxt)
            pause(0.5, 1.2)
            nxt.click()
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.b_algo")))
            return True
        except (NoSuchElementException, TimeoutException,
                ElementClickInterceptedException, StaleElementReferenceException):
            return False

    def is_results_page(self, driver: Any) -> bool:
        return "bing.com/search" in driver.current_url
