@echo off
setlocal

:: Set your NordVPN credentials
set NORDVPN_USERNAME=your_username_here
set NORDVPN_PASSWORD=your_password_here
set VPN_LOCATION=USA

:: Download NordVPN
echo Downloading NordVPN...
powershell -Command "Invoke-WebRequest -Uri 'https://downloads.nordcdn.com/apps/windows/10/NordVPN/latest/NordVPNSetup.exe' -OutFile '%UserProfile%\Downloads\NordVPNSetup.exe'"

:: Install NordVPN
echo Installing NordVPN...
start /wait %UserProfile%\Downloads\NordVPNSetup.exe /S

:: Wait for the installation to complete
timeout /t 30 /nobreak > NUL

:: Login to NordVPN
echo Logging into NordVPN...
nordvpn -username %NORDVPN_USERNAME% -password %NORDVPN_PASSWORD%

:: Connect to VPN
echo Connecting to VPN in %VPN_LOCATION%...
nordvpn connect %VPN_LOCATION%

echo Script completed.
endlocal