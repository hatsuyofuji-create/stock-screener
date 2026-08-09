@echo off
cd /d "%~dp0"
echo Starting Tanshin Collector app...
echo If the browser does not open, open http://localhost:8502
python -m streamlit run tanshin_collector.py --server.port 8502
pause
