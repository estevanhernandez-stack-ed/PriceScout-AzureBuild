# Add AMC discount programs
Set-Location "c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react"
$env:PYTHONPATH = "."
& .\.venv\Scripts\python.exe scripts\add_amc_discounts.py
