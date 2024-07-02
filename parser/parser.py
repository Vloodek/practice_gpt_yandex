import time
import json
import sys
import re
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
import psutil
import os
import shutil
import validators
from uniter import remote_call

def get_current_chrome_pids():
    return {process.pid for process in psutil.process_iter() if process.name() in ["chrome", "chromedriver"]}

def close_new_chrome_processes(initial_pids):
    new_pids = get_current_chrome_pids() - initial_pids
    for pid in new_pids:
        try:
            psutil.Process(pid).terminate()
        except psutil.NoSuchProcess:
            continue

def get_page_data(url, initial_pids, profile_path):
    options = uc.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument(f'--user-data-dir={profile_path}')

    max_retries = 3
    for attempt in range(max_retries):
        try:
            driver = uc.Chrome(options=options)
            break
        except WebDriverException:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                raise

    try:
        driver.get(url)
        time.sleep(2)  # Уменьшение времени ожидания для загрузки страницы

        title = driver.title or ''

        try:
            meta_description = driver.find_element(By.NAME, "description").get_attribute("content")
        except:
            meta_description = ''

        try:
            meta_keywords = driver.find_element(By.NAME, "keywords").get_attribute("content")
        except:
            meta_keywords = ''

        headings = []
        for tag in ['h1', 'h2', 'h3']:
            elements = driver.find_elements(By.TAG_NAME, tag)
            for element in elements:
                headings.append(element.text)

    except WebDriverException as e:
        print(f"Error loading page {url}: {e}")
        title = "Error loading page"
        meta_description = ""
        meta_keywords = ""
        headings = ""
    finally:
        driver.quit()
        close_new_chrome_processes(initial_pids)
        shutil.rmtree(profile_path, ignore_errors=True)

    return {
        "url": url,
        "title": title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords,
        "headings": " ".join(headings)
    }

def parse_url(url):
    initial_pids = get_current_chrome_pids()
    profile_path = f"/tmp/chrome_profile_{os.getpid()}"
    os.makedirs(profile_path, exist_ok=True)
    page_data = get_page_data(url, initial_pids, profile_path)

    # Сохранение данных в JSON файл
    with open('parsed_data.json', 'w', encoding='utf-8') as file:
        json.dump(page_data, file, ensure_ascii=False, indent=4)

    print(f"Parsing complete for {url}.")
    remote_call()

def main(url):
    if not validators.url(url):
        print("Ошибка: Некорректный URL")
        sys.exit(1)

    start_time = time.time()
    parse_url(url)
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 parser.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    main(url)
