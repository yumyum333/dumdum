import boto3
import os
from dotenv import load_dotenv
import time
import botocore

# Load environment variables from .env file
load_dotenv()

def launch_instances(image_id, instance_type, vpn_count, non_vpn_count, key_name, security_group_id, vpn_user_data, non_vpn_user_data, region_name):
    # Assuming SECURITY_GROUP_IDS contains the ID of the security group you want to modify
    # security_group_id = SECURITY_GROUP_IDS[0]

    ec2 = boto3.client('ec2', region_name=region_name)

    # Check if the rule already exists
    try:
        rules = ec2.describe_security_group_rules(Filters=[
            {'Name': 'group-id', 'Values': [security_group_id]}
        ])
        for rule in rules['SecurityGroupRules']:
            if rule['FromPort'] == 3389 and rule['ToPort'] == 3389 and rule['IpProtocol'] == 'tcp':
                print("Rule for TCP port 3389 already exists. Skipping rule addition.")
                break
        else:
            # Add the rule if it does not exist
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

    # Launch VPN instances
    if vpn_count > 0:
        try:
            vpn_response = ec2.run_instances(
                ImageId=image_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=vpn_count,
                KeyName=key_name,
                SecurityGroupIds=[security_group_id],
                UserData=vpn_user_data
            )
            print(f"Successfully launched {vpn_count} VPN instances.")
        except Exception as e:
            print(f"An error occurred while launching VPN instances: {str(e)}")

    # Launch non-VPN instances
    if non_vpn_count > 0:
        try:
            non_vpn_response = ec2.run_instances(
                ImageId=image_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=non_vpn_count,
                KeyName=key_name,
                SecurityGroupIds=[security_group_id],
                UserData=non_vpn_user_data
            )
            print(f"Successfully launched {non_vpn_count} non-VPN instances.")
        except Exception as e:
            print(f"An error occurred while launching non-VPN instances: {str(e)}")


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


if __name__ == "__main__":
    
    IMAGE_ID = os.getenv('AMI_IMAGE_ID')
    KEY_NAME = os.getenv('AWS_KEY_NAME')
    # VPC_ID = os.getenv('AWS_VPC_ID')
    URL = os.getenv('URL')
    NORDVPN_USERNAME = os.getenv('NORDVPN_USERNAME')
    NORDVPN_PASSWORD = os.getenv('NORDVPN_PASSWORD')
    SOURCE_EMAIL = os.getenv('SOURCE_EMAIL')
    DESTINATION_EMAIL = os.getenv('DESTINATION_EMAIL')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    REGION_NAME = os.getenv('REGION_NAME')
    INSTANCE_TYPE = os.getenv('INSTANCE_TYPE')
    VPN_COUNT = int(os.getenv('VPN_COUNT'))
    NON_VPN_COUNT = int(os.getenv('NON_VPN_COUNT'))
    GROUP_NAME = os.getenv('GROUP_NAME')
    INTERVAL = int(os.getenv('INTERVAL'))

    DESCRIPTION = "Security group for instance access on all ports from any IP"
    ec2 = boto3.client('ec2', region_name=REGION_NAME)
    security_group_id = create_security_group(
        ec2=ec2, 
        group_name=GROUP_NAME, 
        description=DESCRIPTION, 
        # vpc_id=VPC_ID,
        )
    
    # Common Operations for All Instances (Non-VPN and VPN)
    COMMON_USER_DATA_1 = f"""#!/bin/bash
    # Install desktop environment and XRDP
    apt-get update
    apt-get install -y xfce4 xfce4-session xrdp
    systemctl enable xrdp
    systemctl start xrdp

    # Install Python and virtual environment tools
    apt-get install -y python3-pip python3-venv

    # Create a Python virtual environment and install dependencies
    python3 -m venv /home/ubuntu/venv
    source /home/ubuntu/venv/bin/activate
    pip install --upgrade pip
    """

    COMMON_USER_DATA_2 = f"""
    # Download the Python script and requirements.txt (Assuming they are available via a public URL)
    wget https://github.com/yumyum333/dumdum/blob/main/monitor_website.py -P /home/ubuntu/
    wget https://github.com/yumyum333/dumdum/blob/main/requirements.txt -P /home/ubuntu/
    pip install -r /home/ubuntu/requirements.txt

    # Run the Python script with arguments 
    python /home/ubuntu/monitor_website.py --url {URL} --interval {INTERVAL} --source-email {SOURCE_EMAIL} --destination-email {DESTINATION_EMAIL} --email-password {EMAIL_PASSWORD}
    """

    NON_VPN_USER_DATA = COMMON_USER_DATA_1 + """
    echo 'No VPN configured on this instance.'
    """ + COMMON_USER_DATA_2

    VPN_USER_DATA = COMMON_USER_DATA_1 + f"""
    # Additional commands to set up and connect to NordVPN
    echo "Setting up and connecting to NordVPN..."
    wget https://nordvpn.com/download/linux/
    sh nordvpn-release_1.0.0_all.deb
    apt-get update
    apt-get install nordvpn
    nordvpn login --username {NORDVPN_USERNAME} --password {NORDVPN_PASSWORD}
    nordvpn connect
    """ + COMMON_USER_DATA_2

    launch_instances(IMAGE_ID, INSTANCE_TYPE, VPN_COUNT, NON_VPN_COUNT, KEY_NAME, security_group_id, VPN_USER_DATA, NON_VPN_USER_DATA, REGION_NAME)
