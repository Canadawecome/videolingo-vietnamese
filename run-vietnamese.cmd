@echo off
cd /d "%~dp0"
python -m streamlit run upgrade_app_vi.py --server.address 127.0.0.1 --server.port 8510
pause
