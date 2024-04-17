import argparse
from selenium import webdriver
from bs4 import BeautifulSoup
import time

def monitor_website(url, check_interval=60):
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        driver = webdriver.Chrome(executable_path='/usr/local/bin/chromedriver', options=options)
        driver.get(url)

        initial_content = driver.page_source
        print("Monitoring started...")
        try:
            while True:
                time.sleep(check_interval)
                driver.refresh()
                new_content = driver.page_source
                if new_content != initial_content:
                    print("Change detected!")
                    break
                else:
                    print("No change detected.")
        finally:
            driver.quit()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Monitor a website for changes.')
    parser.add_argument('--url', type=str, required=True, help='The URL of the website to monitor.')
    parser.add_argument('--interval', type=int, default=300, help='Check interval in seconds. Default is 300 seconds.')
    
    args = parser.parse_args()
    
    monitor_website(args.url, args.interval)