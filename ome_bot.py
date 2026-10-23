import time
import random
import os
import threading
import functools
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
    ElementClickInterceptedException,
)
from webdriver_manager.chrome import ChromeDriverManager

# Make every print() flush immediately so Render logs show it
print = functools.partial(print, flush=True)

# ============================================================
# CONFIG
# ============================================================
SITE_URL = "https://ome.gg/app/chat"

MESSAGES = [
    "Hiiii",
    "F",
    "Talk to me on Chitmet gg",
    "Lisaa982",
]

XPATH_GENDER_MALE    = "//button[normalize-space()='Male']"
XPATH_AGE_CHECKBOX   = "//label[contains(., '18 years of age')]//input[@type='checkbox']"
XPATH_TERMS_CHECKBOX = "//label[contains(., 'Terms') and contains(., 'Privacy')]//input[@type='checkbox']"
XPATH_AGREE_BUTTON   = "//button[contains(normalize-space(), \"Let's Go\")]"
XPATH_START_TEXT_CHAT = "//button[contains(normalize-space(), 'Start Text Chat')]"

SEL_MESSAGE_INPUT   = "div[data-composer='true'] textarea"
SEL_SEND_BUTTON     = "div[data-composer='true'] button[aria-label='Send']"
SEL_SKIP_BUTTON     = "header[data-convo-bar='true'] button[aria-label='Skip']"
SEL_CONVO_BAR       = "header[data-convo-bar='true']"

DELAY_BETWEEN_MSGS   = 3.0
DELAY_AFTER_LAST_MSG = (12.0, 15.0)
DELAY_BETWEEN_CYCLES = (2.0, 4.5)
CONNECT_TIMEOUT      = 60
MAX_CYCLES           = 50
TURNSTILE_WAIT       = 120
REDIRECT_TIMEOUT     = 30

# ============================================================
# DRIVER & HELPERS
# ============================================================
def build_driver():
    print("[driver] building options...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    print("[driver] resolving chromedriver...")
    service = Service(ChromeDriverManager().install())
    print("[driver] launching Chrome...")
    driver = webdriver.Chrome(service=service, options=options)
    print("[driver] Chrome launched")

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver

def safe_click(driver, wait, by, selector, timeout=10):
    try:
        el = wait.until(EC.element_to_be_clickable((by, selector)))
        try:
            el.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", el)
        return True
    except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
        print(f"  [click] failed on {selector}: {e}")
        return False

def human_type(element, text):
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(0.02, 0.08))

def complete_onboarding(driver, wait):
    print("[onboarding] starting")
    if not safe_click(driver, wait, By.XPATH, XPATH_GENDER_MALE, timeout=15):
        print("[onboarding] gender button not found")
        return False
    print("[onboarding] male selected")

    try:
        age_cb = wait.until(EC.presence_of_element_located((By.XPATH, XPATH_AGE_CHECKBOX)))
        if not age_cb.is_selected():
            age_cb.click()
        print("[onboarding] 18+ checked")
    except TimeoutException:
        print("[onboarding] 18+ checkbox not found")
        return False

    try:
        terms_cb = wait.until(EC.presence_of_element_located((By.XPATH, XPATH_TERMS_CHECKBOX)))
        if not terms_cb.is_selected():
            terms_cb.click()
        print("[onboarding] terms checked")
    except TimeoutException:
        print("[onboarding] terms checkbox not found")
        return False

    # --- No GateSolve: just wait for the agree button to become enabled ---
    try:
        agree_btn = wait.until(EC.presence_of_element_located((By.XPATH, XPATH_AGREE_BUTTON)))
        print(f"[onboarding] waiting for Turnstile / agree button to become enabled (up to {TURNSTILE_WAIT}s)…")
        end = time.time() + TURNSTILE_WAIT
        while agree_btn.get_attribute("disabled") is not None and time.time() < end:
            time.sleep(1.0)
        if agree_btn.get_attribute("disabled") is not None:
            print(f"[onboarding] agree button still disabled after {TURNSTILE_WAIT}s — aborting")
            return False
        print("[onboarding] agree button is enabled — clicking")
        safe_click(driver, wait, By.XPATH, XPATH_AGREE_BUTTON, timeout=5)
        print("[onboarding] clicked 'I Agree, Let's Go'")
        return True
    except TimeoutException:
        print("[onboarding] agree button not found")
        return False

def wait_for_page_two(driver, timeout=REDIRECT_TIMEOUT):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, XPATH_START_TEXT_CHAT))
        )
        return True
    except TimeoutException:
        return False

def wait_for_convo_bar(driver, timeout):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEL_CONVO_BAR))
        )
        return True
    except TimeoutException:
        return False

def convo_bar_gone(driver):
    return len(driver.find_elements(By.CSS_SELECTOR, SEL_CONVO_BAR)) == 0

def send_message(driver, wait, text):
    try:
        box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SEL_MESSAGE_INPUT)))
        box.click()
        box.clear()
        human_type(box, text)
        time.sleep(random.uniform(0.3, 0.8))
        if not safe_click(driver, wait, By.CSS_SELECTOR, SEL_SEND_BUTTON, timeout=3):
            box.send_keys(Keys.ENTER)
        return True
    except Exception as e:
        print(f"  [send] failed: {e}")
        return False

def one_cycle(driver, wait, cycle_num, first_cycle=False):
    print(f"\n=== cycle {cycle_num} ===")
    if first_cycle:
        if not safe_click(driver, wait, By.XPATH, XPATH_START_TEXT_CHAT, timeout=15):
            print("  could not find 'Start Text Chat'")
            return False
        print("  clicked Start Text Chat")
    else:
        print("  auto-search already running after previous Skip — waiting for match")

    if not wait_for_convo_bar(driver, CONNECT_TIMEOUT):
        print(f"  no match within {CONNECT_TIMEOUT}s — retrying")
        return False
    print("  matched!")

    for i, msg in enumerate(MESSAGES):
        if convo_bar_gone(driver):
            print("  stranger left before we finished")
            return False
        if not send_message(driver, wait, msg):
            print(f"  failed sending message {i+1}")
            return False
        print(f"  sent: {msg!r}")
        time.sleep(DELAY_BETWEEN_MSGS)

    hold = random.uniform(*DELAY_AFTER_LAST_MSG)
    print(f"  holding chat for {hold:.1f}s before skip…")
    time.sleep(hold)

    if not safe_click(driver, wait, By.CSS_SELECTOR, SEL_SKIP_BUTTON, timeout=8):
        print("  skip failed — reloading")
        driver.get(SITE_URL)
        time.sleep(3)
        complete_onboarding(driver, wait)
        wait_for_page_two(driver)
        safe_click(driver, wait, By.XPATH, XPATH_START_TEXT_CHAT, timeout=15)
    return True

def run_bot():
    print("[bot] run_bot thread started")
    driver = None
    try:
        driver = build_driver()
        print("[bot] driver ready — navigating")
        wait = WebDriverWait(driver, 15)
        searching = False

        driver.get(SITE_URL)
        print("[bot] page loaded:", driver.title)
        time.sleep(random.uniform(2, 4))

        if not complete_onboarding(driver, wait):
            print("Onboarding failed — aborting.")
            return

        print("Waiting for redirect to page 2 (Start Text Chat)…")
        if not wait_for_page_two(driver, timeout=REDIRECT_TIMEOUT):
            print("Never reached page 2 — aborting.")
            return
        print("Landed on page 2 (Start Text Chat).")
        time.sleep(random.uniform(1.5, 3.0))

        for i in range(1, MAX_CYCLES + 1):
            try:
                ok = one_cycle(driver, wait, i, first_cycle=(not searching))
                if ok:
                    searching = True
            except WebDriverException as e:
                print(f"[cycle {i}] webdriver error: {e} — recovering")
                searching = False
                try:
                    driver.get(SITE_URL)
                    time.sleep(3)
                except Exception:
                    print("driver dead, restarting")
                    try: driver.quit()
                    except Exception: pass
                    driver = build_driver()
                    wait = WebDriverWait(driver, 15)
                    driver.get(SITE_URL)
                    time.sleep(3)
            except Exception as e:
                print(f"[cycle {i}] unexpected error: {e}")
            time.sleep(random.uniform(*DELAY_BETWEEN_CYCLES))
    except KeyboardInterrupt:
        print("\nstopped by user")
    except Exception as e:
        print(f"[bot] fatal error: {e}")
    finally:
        if driver:
            try: driver.quit()
            except Exception: pass

# ============================================================
# FLASK HEALTH CHECK
# ============================================================
app = Flask(__name__)

@app.route("/")
def health():
    return "ome bot running", 200

if __name__ == "__main__":
    print("[main] starting bot thread")
    threading.Thread(target=run_bot, daemon=True).start()
    print("[main] bot thread launched, starting Flask")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
