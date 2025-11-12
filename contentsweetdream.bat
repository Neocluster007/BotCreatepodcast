@echo off
echo Starting Podcast Bot...

:: 1. Change to the correct drive and directory
:: The /d switch is important for changing the drive (from C: to E:)
cd /d "e:/BOT/BotCreatepodcast/"

echo Now in directory: %cd%
echo ====================================
echo Running Python script...

:: 2. Run your Python script
:: !!! --- สำคัญ: แก้ไข 'your_script.py' เป็นชื่อไฟล์ .py ของคุณ --- !!!
C:/Users/Neocluster/AppData/Local/Programs/Python/Python310/python.exe e:/BOT/BotCreatepodcast/main.py

echo ====================================
echo Script finished.

:: Keep the window open to see the output
pause