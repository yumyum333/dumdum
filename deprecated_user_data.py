USER_DATA = """#!/bin/bash
# Update and install necessary components
apt-get update
apt-get install -y xfce4 xfce4-session xrdp openvpn easy-rsa

# Set up XRDP to use XFCE
echo xfce4-session >~/.xsession
systemctl enable xrdp
systemctl start xrdp

# Set up Easy-RSA for OpenVPN configuration
make-cadir ~/openvpn-ca
cd ~/openvpn-ca

# Initialize the PKI (Public Key Infrastructure)
./easyrsa init-pki
./easyrsa build-ca nopass

# Generate server certificate and key
./easyrsa gen-req server nopass
./easyrsa sign-req server server

# Generate client certificate and key
./easyrsa build-client-full client1 nopass

# Generate Diffie-Hellman parameters
./easyrsa gen-dh

# Move the certificates
cp pki/private/server.key /etc/openvpn/
cp pki/issued/server.crt /etc/openvpn/
cp pki/ca.crt /etc/openvpn/
cp pki/dh.pem /etc/openvpn/

# Generate server config
echo 'port 1194
dev tun
proto udp
server 10.8.0.0 255.255.255.0
ca ca.crt
cert server.crt
key server.key  # This file should be kept secret
dh dh.pem
keepalive 10 120
cipher AES-256-CBC
user nobody
group nogroup
persist-key
persist-tun
status openvpn-status.log
verb 3' > /etc/openvpn/server.conf

# Start OpenVPN server
systemctl start openvpn@server
systemctl enable openvpn@server

# Adjust firewall
ufw allow 1194/udp
ufw allow OpenSSH
ufw enable
"""

# Include the above USER_DATA in your launch_instances function as previously described.
