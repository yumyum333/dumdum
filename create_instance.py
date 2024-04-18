import boto3
import os
from dotenv import load_dotenv
import time
import botocore
import random
from datetime import datetime
import paramiko
import asyncio
from tqdm import tqdm


# Load environment variables from .env file
load_dotenv()

def launch_instances(image_id, instance_type, count, key_name, security_group_id, user_data, region_name):
    print("Initializing EC2 client...")
    ec2 = boto3.client('ec2', region_name=region_name)

    # Check if the rule already exists
    try:
        print("Checking for existing security group rules...")
        rules = ec2.describe_security_group_rules(Filters=[
            {'Name': 'group-id', 'Values': [security_group_id]}
        ])
        for rule in rules['SecurityGroupRules']:
            if rule['FromPort'] == 3389 and rule['ToPort'] == 3389 and rule['IpProtocol'] == 'tcp':
                print("Rule for TCP port 3389 already exists. Skipping rule addition.")
                break
        else:
            # Add the rule if it does not exist
            print("Adding new rule for TCP port 3389...")
            ec2.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3389,
                        'ToPort': 3389,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                    },
                ],
            )
            print("Ingress rule for TCP port 3389 set successfully.")
    except botocore.exceptions.ClientError as e:
        print(f"An error occurred: {e}")
        raise

    # Launch instances
    try:
        exp_time = datetime.now().strftime("%H%M-%S-%b%d")
        print(f"Launching {count} instances...")
        response = ec2.run_instances(
            ImageId=image_id,
            InstanceType=instance_type,
            MinCount=1,
            MaxCount=count,
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            UserData=user_data,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': f'{exp_time}'
                        }
                    ]
                }
            ]
        )
        print(f"Successfully launched {count} instances.")
        return [instance['InstanceId'] for instance in response['Instances']]
    except Exception as e:
        print(f"An error occurred while launching instances: {str(e)}")
        return []


def get_default_vpc_id(ec2):
    response = ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    default_vpc = response['Vpcs'][0]  # Assuming there is always one default VPC
    return default_vpc['VpcId']

def create_security_group(ec2, group_name, description, vpc_id=None):
    """Create a security group and open required ports, or return existing one if it already exists."""
    if vpc_id is None:
        vpc_id = get_default_vpc_id(ec2)

    # Check if the security group already exists
    try:
        existing_groups = ec2.describe_security_groups(Filters=[
            {'Name': 'group-name', 'Values': [group_name]},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ])
        if existing_groups['SecurityGroups']:
            existing_group_id = existing_groups['SecurityGroups'][0]['GroupId']
            print(f"Security Group '{group_name}' already exists with ID: {existing_group_id}")
            return existing_group_id
    except botocore.exceptions.ClientError as e:
        print(f"Failed to check for existing security groups: {e}")
        raise

    # Create new security group
    print("Creating a new security group...")
    response = ec2.create_security_group(GroupName=group_name, Description=description, VpcId=vpc_id)
    security_group_id = response['GroupId']
    print(f'Security Group Created: {security_group_id} in vpc {vpc_id}.')

    # Set up the security group rules to allow inbound SSH, RDP, and possibly VPN traffic
    ec2.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=[
            {'IpProtocol': 'tcp',
             'FromPort': 22,
             'ToPort': 22,
             'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
            {'IpProtocol': 'tcp',
             'FromPort': 3389,
             'ToPort': 3389,
             'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
            {'IpProtocol': 'udp',
             'FromPort': 1194,
             'ToPort': 1194,
             'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},  # For VPN traffic
        ]
    )
    return security_group_id


async def main():
    
    IMAGE_ID = os.getenv('AMI_IMAGE_ID')
    KEY_NAME = os.getenv('AWS_KEY_NAME')
    URL = os.getenv('URL')
    NORDVPN_USERNAME = os.getenv('NORDVPN_USERNAME')
    NORDVPN_PASSWORD = os.getenv('NORDVPN_PASSWORD')
    REGION_NAME = os.getenv('REGION_NAME')
    INSTANCE_TYPE = os.getenv('INSTANCE_TYPE')
    NON_VPN_COUNT = int(os.getenv('NON_VPN_COUNT'))
    GROUP_NAME = os.getenv('GROUP_NAME')
    INTERVAL = int(os.getenv('INTERVAL'))
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
    LOG_GROUP = os.getenv('LOG_GROUP')
    LOG_STREAM = os.getenv('LOG_STREAM')
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    KEY_PATH = os.getenv('KEY_PATH')

    DESCRIPTION = "Security group for instance access on all ports from any IP"
    ec2 = boto3.client('ec2', region_name=REGION_NAME)
    security_group_id = create_security_group(
        ec2=ec2, 
        group_name=GROUP_NAME, 
        description=DESCRIPTION, 
    )
        
    # Static part of the PowerShell script
    USER_DATA = r"""
    <powershell>
    # Set the Administrator password (ensure it meets complexity requirements)
    net user Administrator "{admin_password}"

    
    # Enable RDP
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -name "fDenyTSConnections" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

    # Allow RDP through Windows Firewall
    netsh advfirewall firewall set rule group="remote desktop" new enable=Yes

    # Install Python and virtual environment tools
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.9.7/python-3.9.7-amd64.exe" -OutFile "C:\Users\Administrator\Desktop\python-installer.exe"
    Start-Process -FilePath "C:\Users\Administrator\Desktop\python-installer.exe" -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait
    Remove-Item "C:\Users\Administrator\Desktop\python-installer.exe"

    # Download the Python script and requirements.txt to the Desktop
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/yumyum333/dumdum/main/monitor_website.py" -OutFile "C:\Users\Administrator\Desktop\monitor_website.py"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/yumyum333/dumdum/main/requirements.txt" -OutFile "C:\Users\Administrator\Desktop\requirements.txt"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/yumyum333/dumdum/main/vpn_install.bat" -OutFile "C:\Users\Administrator\Desktop\vpn_install.bat"



    </powershell>
    """.replace("{admin_password}", ADMIN_PASSWORD).replace("{URL}", URL).replace("{INTERVAL}", str(INTERVAL)).replace("{LOG_GROUP}", LOG_GROUP).replace("{LOG_STREAM}", LOG_STREAM).replace("{REGION_NAME}", REGION_NAME).replace("{AWS_ACCESS_KEY_ID}", AWS_ACCESS_KEY_ID).replace("{AWS_SECRET_ACCESS_KEY}", AWS_SECRET_ACCESS_KEY)

    instance_ids = launch_instances(IMAGE_ID, INSTANCE_TYPE, NON_VPN_COUNT, KEY_NAME, security_group_id, USER_DATA, REGION_NAME)

if __name__ == '__main__':
    asyncio.run(main())
