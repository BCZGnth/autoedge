"""Default SearchTarget: a local mock search site, so the default run mode
never makes a live network call. Selection/pacing/typing behavior all still
goes through the normal driving loop -- only the site being searched is
fake.
"""

from __future__ import annotations

from typing import Any

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..interaction import human_type, pause
from ..mock_server import MockSearchServer
from .base import SearchTarget


class MockTarget(SearchTarget):
    name = "mock"

    def __init__(self, host: str = "127.0.0.1"):
        self._server = MockSearchServer(host).start()

    @property
    def home_url(self) -> str:
        return self._server.url("/")

    def ensure_ready(self, driver: Any) -> None:
        driver.get(self.home_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "q")))

    def submit_search(self, driver: Any, query: str) -> None:
        driver.get(self.home_url)
        box = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "q")))
        box.click()
        human_type(box, query)
        pause(0.3, 0.9)
        box.send_keys(Keys.RETURN)
        WebDriverWait(driver, 10).until(lambda d: self.is_results_page(d))

    def result_links(self, driver: Any) -> list:
        return driver.find_elements(By.CSS_SELECTOR, "a.result-link")

    def goto_next_page(self, driver: Any) -> bool:
        try:
            nxt = driver.find_element(By.ID, "next-page")
        except NoSuchElementException:
            return False
        nxt.click()
        WebDriverWait(driver, 10).until(lambda d: self.is_results_page(d))
        return True

    def is_results_page(self, driver: Any) -> bool:
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            return body.get_attribute("data-page") == "results"
        except NoSuchElementException:
            return False

    def stop(self) -> None:
        self._server.stop()
