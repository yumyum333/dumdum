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


def connect_to_instance(instance_id, key_path, region_name, security_group_id):
    ec2_resource = boto3.resource('ec2', region_name=region_name)
    instance = ec2_resource.Instance(instance_id)
    
    # Wait until the instance is in a running state
    print(f"Waiting for instance {instance_id} to be in 'running' state...")
    instance.wait_until_running()
    print(f"Instance {instance_id} is now running.")

    # Get the public IP address of the instance
    public_ip = instance.public_ip_address
    if not public_ip:
        print(f"No public IP address assigned to instance {instance_id}.")
        return None

    # Create an SSH client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Connect to the instance using password
    admin_password = os.getenv('ADMIN_PASSWORD')  # Ensure this environment variable is correctly set
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            print(f"Attempt {attempt + 1}: Connecting to instance...\nID: {instance_id}\nIP: {public_ip}\nSecurity group: {security_group_id}\nKey: {key_path}")
            ssh.connect(hostname=public_ip, username="Administrator", password=admin_password, key_filename=key_path, timeout=30)
            print("SSH connection established.")
            return ssh
        except paramiko.ssh_exception.NoValidConnectionsError as e:
            print(f"Failed to connect to instance {instance_id}: {e}")
            if attempt < max_attempts - 1:
                print("Retrying in 30 seconds...")
                time.sleep(30)
            else:
                print("Maximum retry attempts reached, failing...")
                return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None

    return None

def run_commands_on_instance(ssh, commands):
    print("Running commands on the instance...")
    for command in commands:
        stdin, stdout, stderr = ssh.exec_command(command)
        print(f"Command: {command}")
        print(f"Output: {stdout.read().decode('utf-8')}")
        print(f"Error: {stderr.read().decode('utf-8')}")


async def connect_and_run_commands(instance_id, key_path, region_name, commands, security_group_id):
    print(f"Connecting to instance: {instance_id}")
    ssh = connect_to_instance(instance_id, key_path, region_name, security_group_id)
    if ssh is None:
        print(f"Failed to establish SSH connection to instance {instance_id}. Skipping command execution.")
        return

    await asyncio.gather(*[asyncio.to_thread(run_commands_on_instance, ssh, [command]) for command in commands])

    ssh.close()

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
        
    USER_DATA = rf"""
    <powershell>
    # Set the Administrator password (ensure it meets complexity requirements)
    net user Administrator "{ADMIN_PASSWORD}"

    # Enable RDP
    Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -name "fDenyTSConnections" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

    # Allow RDP through Windows Firewall
    netsh advfirewall firewall set rule group="remote desktop" new enable=Yes

    # Install and configure OpenSSH Server
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
    Start-Service sshd
    Set-Service -Name sshd -StartupType 'Automatic'

    # Configure SSH to use the default user profile
    $sshConfPath = "$env:ProgramData\ssh\sshd_config"
    $sshConfContent = Get-Content -Path $sshConfPath
    $sshConfContent += "`nMatch User Administrator`n    ForceCommand powershell.exe"
    Set-Content -Path $sshConfPath -Value $sshConfContent
    Restart-Service sshd

    # Install Python and virtual environment tools
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.9.7/python-3.9.7-amd64.exe" -OutFile "C:\Users\Administrator\Desktop\python-installer.exe"
    Start-Process -FilePath "C:\Users\Administrator\Desktop\python-installer.exe" -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait
    Remove-Item "C:\Users\Administrator\Desktop\python-installer.exe"

    # Download the Python script and requirements.txt to the Desktop
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/yumyum333/dumdum/main/monitor_website.py" -OutFile "C:\Users\Administrator\Desktop\monitor_website.py"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/yumyum333/dumdum/main/requirements.txt" -OutFile "C:\Users\Administrator\Desktop\requirements.txt"

    </powershell>
    """

    instance_ids = launch_instances(IMAGE_ID, INSTANCE_TYPE, NON_VPN_COUNT, KEY_NAME, security_group_id, USER_DATA, REGION_NAME)

    if instance_ids:
        print(f"Instances launched successfully. Instance IDs: {instance_ids}")

        commands = [
            'cd Desktop',
            'pip install -r requirements.txt',
            'ex --remote-debugging-port=9222 "{URL}"',
            'timeout /t 10',
            f'python monitor_website.py --url {URL} --interval {INTERVAL} --log-group {LOG_GROUP} --log-stream {LOG_STREAM} --region-name {REGION_NAME} --aws-access-key-id {AWS_ACCESS_KEY_ID} --aws-secret-access-key {AWS_SECRET_ACCESS_KEY}'
        ]

        await asyncio.gather(*[connect_and_run_commands(instance_id, KEY_PATH, REGION_NAME, commands, security_group_id) for instance_id in instance_ids])
    else:
        print("Failed to launch instances.")

if __name__ == '__main__':
    asyncio.run(main())
