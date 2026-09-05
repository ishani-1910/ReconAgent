import os
import time
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

ARTIFACT_DIR = r"C:\Users\Oscar\.gemini\antigravity-ide\brain\13d2641b-75f9-4881-9d4a-e757ada7414d\scratch"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1600,1200")
options.add_argument("--disable-gpu")

driver = webdriver.Edge(options=options)
try:
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    print("Navigating to http://localhost:8501...")
    driver.get("http://localhost:8501")
    wait = WebDriverWait(driver, 20)
    
    # Click on the 3rd tab: Leg 2 Cash Settlement Matrix
    tab_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Leg 2: Cash Settlement Matrix')]")))
    driver.execute_script("arguments[0].click();", tab_btn)
    print("Clicked Leg 2 Cash Settlement Matrix tab")
    time.sleep(3)

    # Screenshot Tab 3
    path3 = os.path.join(ARTIFACT_DIR, "tab3_ground_truth_accuracy.png")
    driver.save_screenshot(path3)
    print(f"Saved Tab 3 Ground-Truth Screenshot: {path3}")

finally:
    driver.quit()
