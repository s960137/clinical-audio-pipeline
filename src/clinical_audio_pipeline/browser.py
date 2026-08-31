"""Optional authorized browser adapter; no credentials or profiles are persisted."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from .download import checked_url
from .tables import RECORDING_COLUMNS, opaque_id, timestamp


def collect_manifest(config_path, output, browser="edge"):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    output = Path(output)
    if output.exists():
        raise ValueError("Manifest already exists; select a new output path")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    url = checked_url(config["records_url"], config["allowed_hosts"])
    expected_origin = urlsplit(url)[:2]
    driver = webdriver.Edge() if browser == "edge" else webdriver.Chrome()
    entries = []
    seen = set()
    try:
        driver.get(url)
        input("Sign in manually if needed, open the recordings page, then press Enter here: ")
        for page in range(config.get("max_pages", 100)):
            if urlsplit(driver.current_url)[:2] != expected_origin:
                raise ValueError("Browser left the configured origin; collection stopped")
            rows = WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, config["row_selector"])))
            for row in rows:
                rid = opaque_id(row.get_attribute(config["recording_id_attribute"]) or "")
                if rid in seen:
                    raise ValueError("Repeated recording identifier or pagination loop; no manifest written")
                seen.add(rid)
                subject = opaque_id(row.get_attribute(config["subject_id_attribute"]) or "")
                time = row.get_attribute(config["timestamp_attribute"]) or ""
                timestamp(time)
                source_url = row.find_element(By.CSS_SELECTOR, config["audio_selector"]).get_attribute("href")
                checked_url(source_url or "", config["allowed_hosts"])
                entries.append([rid, subject, time, source_url])
            next_buttons = driver.find_elements(By.CSS_SELECTOR, config["next_selector"])
            if not next_buttons or not next_buttons[0].is_enabled() or \
                    next_buttons[0].get_attribute("aria-disabled") == "true":
                break
            if page + 1 == config.get("max_pages", 100):
                raise ValueError("Page limit reached; no truncated manifest written")
            previous_first = rows[0].get_attribute(config["recording_id_attribute"])
            next_buttons[0].click()

            def page_changed(current_driver):
                found = current_driver.find_elements(By.CSS_SELECTOR, config["row_selector"])
                return found and found[0].get_attribute(config["recording_id_attribute"]) != previous_first

            WebDriverWait(driver, 20).until(page_changed)
        if not entries:
            raise ValueError("No recordings found")
        table = pd.DataFrame(entries, columns=RECORDING_COLUMNS)
        if table.source_url.duplicated().any():
            raise ValueError("Duplicate source URL; review the source before export")
        output.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(output, index=False, encoding="utf-8-sig", mode="x")
        return {"recordings": len(table)}
    finally:
        driver.quit()
