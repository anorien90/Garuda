# unchanged logic; kept for completeness (headless toggle & fast-load prefs)
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException


class SeleniumBrowser:
    def __init__(self, headless: bool = True, timeout: int = 10):
        self.timeout = timeout
        self.driver = None
        self.headless = headless
        self.logger = logging.getLogger(__name__)
    
    def __enter__(self):
        self._init_driver()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def _init_driver(self):
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
        }
        options.add_experimental_option("prefs", prefs)
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(self.timeout)
    
    def get_page(self, url: str, wait_for_selector: Optional[str] = None) -> str:
        try:
            self.driver.get(url)
            if wait_for_selector:
                WebDriverWait(self.driver, self.timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                )
            else:
                WebDriverWait(self.driver, min(3, self.timeout)).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            time.sleep(0.5)
            return self.driver.page_source
        except TimeoutException:
            self.logger.debug(f"Timeout loading:  {url}")
            return self.driver.page_source if self.driver else ""
        except WebDriverException as e:
            self.logger.debug(f"WebDriver error for {url}: {e}")
            return ""
    
    def find_links(self, base_url: str) -> List[Dict[str, str]]:
        links = []
        seen_hrefs = set()
        try:
            elements = self.driver.find_elements(By.TAG_NAME, "a")
            for elem in elements:
                try:
                    href = elem.get_attribute("href")
                    text = elem.text.strip()
                    if href and href not in seen_hrefs:
                        if not href.startswith(("http://", "https://")):
                            href = urljoin(base_url, href)
                        seen_hrefs.add(href)
                        links.append({"href": href, "text": text})
                except Exception:
                    continue
        except Exception as e:
            self.logger.debug(f"Error finding links:  {e}")
        return links
    
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
