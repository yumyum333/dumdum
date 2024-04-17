import boto3

def launch_instances(image_id, instance_type, vpn_count, non_vpn_count, key_name, security_group_id, vpn_user_data, non_vpn_user_data):
    # Assuming SECURITY_GROUP_IDS contains the ID of the security group you want to modify
    # security_group_id = SECURITY_GROUP_IDS[0]

    ec2 = boto3.client('ec2')

    # Add a rule to allow inbound RDP traffic from any IP address
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
    # Launch VPN instances
    if vpn_count > 0:
        try:
            vpn_response = ec2.run_instances(
                ImageId=image_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=vpn_count,
                KeyName=key_name,
                SecurityGroupIds=security_group_id,
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
                SecurityGroupIds=security_group_id,
                UserData=non_vpn_user_data
            )
            print(f"Successfully launched {non_vpn_count} non-VPN instances.")
        except Exception as e:
            print(f"An error occurred while launching non-VPN instances: {str(e)}")

def create_security_group(ec2, vpc_id, group_name, description):
    """Create a security group and open required ports."""
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
    IMAGE_ID = 'ami-0abcdef1234567890'
    INSTANCE_TYPE = 't2.micro'
    VPN_COUNT = 0  # Number of VPN instances
    NON_VPN_COUNT = 9  # Number of non-VPN instances
    KEY_NAME = 'YourKeyName'
    # SECURITY_GROUP_IDS = ['sg-0123456789abcdef0']
    ec2 = boto3.client('ec2')
    VPC_ID = 'your-vpc-id'  # Replace with your VPC ID
    GROUP_NAME = "OpenAllPortsGroup"
    DESCRIPTION = "Security group for instance access on all ports from any IP"
    security_group_id = create_security_group(ec2, VPC_ID, GROUP_NAME, DESCRIPTION)

    # Common Operations for All Instances (Non-VPN and VPN)
    COMMON_USER_DATA = """#!/bin/bash
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

    # Download the Python script and requirements.txt (Assuming they are available via a public URL)
    wget https://github.com/yumyum333/dumdum/blob/main/monitor_website.py -P /home/ubuntu/
    wget https://github.com/yumyum333/dumdum/blob/main/requirements.txt -P /home/ubuntu/
    pip install -r /home/ubuntu/requirements.txt

    # Run the Python script with arguments 
    python /home/ubuntu/monitor_website.py --arg1 'Value1' --arg2 'Value2'
    """
    # TODO: fix args, and storage of the script and requirements.txt

    NON_VPN_USER_DATA = COMMON_USER_DATA + """
    echo 'No VPN configured on this instance.'
    """

    VPN_USER_DATA = COMMON_USER_DATA + """
    # Additional commands to set up and connect to NordVPN
    echo "Setting up and connecting to NordVPN..."
    wget https://nordvpn.com/download/linux/
    sh nordvpn-release_1.0.0_all.deb
    apt-get update
    apt-get install nordvpn
    nordvpn login --username your_username --password your_password
    nordvpn connect
    """

    # launch_instances(IMAGE_ID, INSTANCE_TYPE, VPN_COUNT, NON_VPN_COUNT, KEY_NAME, SECURITY_GROUP_IDS, VPN_USER_DATA, NON_VPN_USER_DATA)

    launch_instances(IMAGE_ID, INSTANCE_TYPE, VPN_COUNT, NON_VPN_COUNT, KEY_NAME, security_group_id, VPN_USER_DATA, NON_VPN_USER_DATA)
