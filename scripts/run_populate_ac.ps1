Set-Location "c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react"
$env:PYTHONPATH = "."
& .\.venv\Scripts\python.exe scripts\populate_ac_pricing.py
