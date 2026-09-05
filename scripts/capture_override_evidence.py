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
    
    # Wait for tabs to appear
    tab_elem = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Auditor Exception Workbench')]")))
    print("Found Auditor Exception Workbench tab")
    driver.execute_script("arguments[0].click();", tab_elem)
    time.sleep(3)

    # Find Decision Station header and scroll into view for stmt_101
    station_hdr1 = wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Auditor Decision Station')]")))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", station_hdr1)
    time.sleep(2)

    # Screenshot 1: stmt_101 (Locked)
    path1 = os.path.join(ARTIFACT_DIR, "guard_locked_stmt101.png")
    driver.save_screenshot(path1)
    print(f"Saved Screenshot 1 (stmt_101 locked): {path1}")

    # Find the selectbox for Bank Stmt ID
    sb = driver.find_element(By.XPATH, "//div[@data-testid='stSelectbox']")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sb)
    time.sleep(1)
    sb.click()
    time.sleep(1)

    # Type or click stmt_102
    inp = sb.find_element(By.XPATH, ".//input")
    inp.send_keys("stmt_102")
    inp.send_keys(Keys.ENTER)
    print("Selected stmt_102")
    time.sleep(3)

    # Scroll to Decision Station for stmt_102
    station_hdr2 = wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Auditor Decision Station')]")))
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", station_hdr2)
    time.sleep(2)

    # Screenshot 2: stmt_102 (Active form)
    path2 = os.path.join(ARTIFACT_DIR, "guard_active_stmt102.png")
    driver.save_screenshot(path2)
    print(f"Saved Screenshot 2 (stmt_102 active): {path2}")

finally:
    driver.quit()
