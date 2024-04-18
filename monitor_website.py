import argparse
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.edge.options import Options
import time
import socket
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import boto3
import os

def get_ip_and_hostname():
    print(f"Hostname: {hostname}, Private IP: {private_ip_address}, Public IP: {public_ip_address}")
    hostname = socket.gethostname()
    private_ip_address = socket.gethostbyname(hostname)
    try:
        # Fetch the public IP from AWS metadata service
        public_ip_address = requests.get('http://169.254.169.254/latest/meta-data/public-ipv4', timeout=2).text
        public_ipv4_dns = requests.get('http://169.254.169.254/latest/meta-data/public-hostname', timeout=2).text
    except requests.RequestException:
        # Fallback if not running on AWS or if the request fails
        public_ip_address = "Unavailable"
        public_ipv4_dns = "Unavailable"
    return hostname, private_ip_address, public_ip_address, public_ipv4_dns

def send_cloudwatch_log(region_name, log_group, log_stream, message, aws_access_key_id, aws_secret_access_key):
    client = boto3.client('logs', region_name=region_name, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
    print(f"Sending log to CloudWatch: {message}")
    try:
        response = client.describe_log_streams(logGroupName=log_group)
        log_streams = response['logStreams']
        sequence_token = None
        for stream in log_streams:
            if stream['logStreamName'] == log_stream:
                if 'uploadSequenceToken' in stream:
                    sequence_token = stream['uploadSequenceToken']
                break

        log_event = {
            'logGroupName': log_group,
            'logStreamName': log_stream,
            'logEvents': [
                {
                    'timestamp': int(time.time() * 1000),
                    'message': message
                },
            ],
        }
        if sequence_token:
            log_event['sequenceToken'] = sequence_token

        client.put_log_events(**log_event)
        print("Log sent to CloudWatch")
    except client.exceptions.ResourceNotFoundException:
        print("Log group or stream not found")
    except Exception as e:
        print(f"Failed to send log to CloudWatch: {e}")

def monitor_website(url, check_interval, log_group, log_stream, region_name, aws_access_key_id, aws_secret_access_key):
    hostname, private_ip_address, public_ip_address, public_ipv4_dns = get_ip_and_hostname()
    debug_message = "instance opened the browser successfully."
    email_message = f"CHANGE DETECTED!\n\nPublic IPV4 DNS:\n{public_ipv4_dns}\n\nHostname:\n{hostname}\n\nPrivate IP Address:\n{private_ip_address}\n\nPublic IP Address:\n{public_ip_address}"
      
    try:
        options = Options()
        options.add_experimental_option("debuggerAddress", "localhost:9222")
        driver = webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=options)
        print("WebDriver options set.")
        # Switch to the first tab (index 0)
        driver.switch_to.window(driver.window_handles[0])
        print("Connteted to the browser successfully.")
        driver.get(url)
        print(f"Opening the URL: {url}")

        initial_content = driver.page_source
        print("Initial page content fetched.")
        send_cloudwatch_log(region_name, log_group, log_stream, debug_message, aws_access_key_id, aws_secret_access_key)
        count = 0
        try:
            while True:
                time.sleep(check_interval)
                driver.refresh()
                new_content = driver.page_source
                if new_content != initial_content or count >= 10:
                    send_cloudwatch_log(region_name, log_group, log_stream, email_message, aws_access_key_id, aws_secret_access_key)
                    break
                else:
                    print(f"Check {count}: Content checked, no change detected.")
                    count += 1
        finally:
            driver.quit()
            print("Quitting the driver.")
    except Exception as e:
        error_message = f"error: {e}"
        print(error_message)
        send_cloudwatch_log(region_name, log_group, log_stream, error_message, aws_access_key_id, aws_secret_access_key)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Monitor a website for changes.')
    parser.add_argument('--url', type=str, required=True, help='The URL of the website to monitor.')
    parser.add_argument('--interval', type=int, default=300, help='Check interval in seconds. Default is 300 seconds.')
    parser.add_argument('--log-group', type=str, required=True, help='The CloudWatch log group name.')
    parser.add_argument('--log-stream', type=str, required=True, help='The CloudWatch log stream name.')
    parser.add_argument('--region-name', type=str, default="eu-west-2", help='The AWS region name. Default is "eu-west-2".')
    parser.add_argument('--aws-access-key-id', type=str, required=True, help='The AWS access key ID.')
    parser.add_argument('--aws-secret-access-key', type=str, required=True, help='The AWS secret access key.')
    
    args = parser.parse_args()
    
    monitor_website(args.url, args.interval, args.log_group, args.log_stream, args.region_name, args.aws_access_key_id, args.aws_secret_access_key)