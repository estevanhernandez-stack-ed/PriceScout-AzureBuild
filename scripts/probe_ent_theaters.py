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
        
    theaters = client.get_theaters(theater_names=["Marcus Ridge Cinema"])
    if theaters:
        t = theaters[0]
        print(json.dumps(t, indent=2))
    else:
        print("No theater found")

if __name__ == "__main__":
    probe()
