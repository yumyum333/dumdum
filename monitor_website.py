import argparse
from selenium import webdriver
import time
import socket
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

def get_ip_and_hostname():
    hostname = socket.gethostname()
    private_ip_address = socket.gethostbyname(hostname)
    try:
        # Fetch the public IP from AWS metadata service
        public_ip_address = requests.get('http://169.254.169.254/latest/meta-data/public-ipv4', timeout=2).text
    except requests.RequestException:
        # Fallback if not running on AWS or if the request fails
        public_ip_address = "Unavailable"
    return hostname, private_ip_address, public_ip_address

def send_email(source_email, destination_email, email_password, message):
    msg = MIMEMultipart()
    msg['From'] = source_email
    msg['To'] = destination_email
    msg['Subject'] = 'CHANGE DETECTED'
    msg.attach(MIMEText(message, 'plain'))
    
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(source_email, email_password)
    text = msg.as_string()
    server.sendmail(source_email, destination_email, text)
    server.quit()

def monitor_website(url, check_interval, source_email, destination_email, email_password):
    hostname, private_ip_address, public_ip_address = get_ip_and_hostname()
    email_message = f"CHANGE DETECTED\n\nHostname:\n{hostname}\n\nPrivate IP Address:\n{private_ip_address}\n\nPublic IP Address:\n{public_ip_address}"
    
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        driver = webdriver.Chrome(executable_path='/usr/local/bin/chromedriver', options=options)
        driver.get(url)

        initial_content = driver.page_source
        print(email_message)
        send_email(source_email, destination_email, email_password, email_message)
        
        try:
            while True:
                time.sleep(check_interval)
                driver.refresh()
                new_content = driver.page_source
                if new_content != initial_content:
                    print("Change detected!")
                    send_email(source_email, destination_email, email_password, "Change detected at " + url)
                    break
                else:
                    print("No change detected.")
        finally:
            driver.quit()
    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(error_message)
        send_email(source_email, destination_email, email_password, error_message)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Monitor a website for changes.')
    parser.add_argument('--url', type=str, required=True, help='The URL of the website to monitor.')
    parser.add_argument('--interval', type=int, default=300, help='Check interval in seconds. Default is 300 seconds.')
    parser.add_argument('--source-email', type=str, required=True, help='The source email address for the email.')
    parser.add_argument('--destination-email', type=str, required=True, help='The destination email address for the email.')
    parser.add_argument('--email-password', type=str, required=True, help='The password for the source email account.')
    
    args = parser.parse_args()
    
    monitor_website(args.url, args.interval, args.source_email, args.destination_email, args.email_password)