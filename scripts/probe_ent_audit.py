from enttelligence_client import EntTelligenceClient
import os
import json

def probe():
    client = EntTelligenceClient()
    TOKEN_NAME = os.getenv("ENTTELLIGENCE_TOKEN_NAME", "PriceScoutAzure")
    TOKEN_SECRET = os.getenv("ENTTELLIGENCE_TOKEN_SECRET", "")
    
    if not client.login(TOKEN_NAME, TOKEN_SECRET):
        print("Auth failed")
        return
        
    audit = client.get_programming_audit(start_date="2026-01-14", end_date="2026-01-14")
    if audit:
        print(f"Found {len(audit)} records")
        print(f"Audit record keys: {audit[0].keys()}")
    else:
        print("No audit data for today")

if __name__ == "__main__":
    probe()
