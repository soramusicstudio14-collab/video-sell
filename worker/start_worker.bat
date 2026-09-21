@echo off
cd /d "D:\ALL AUTOMATION FILE\youtube video sell\gift-video-site\worker"
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
pip install python-dotenv -q
python worker.py
pause
