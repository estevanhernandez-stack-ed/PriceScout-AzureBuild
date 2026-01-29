
import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.append(os.getcwd())

from app import config
# Mock config if needed
config.APP_VERSION = "1.0.0"

from api.routers.system import get_system_health, SystemHealthResponse
import asyncio

async def test_health():
    try:
        # We need a dummy user dict for the Depends(require_read_admin)
        # But since we are calling the function directly, we can pass it manually
        dummy_user = {"user_id": 1, "username": "admin", "role": "admin"}
        
        # Call the health check function
        health_data = await get_system_health(current_user=dummy_user)
        
        print("Health Status:", health_data.status)
        print("Version:", health_data.version)
        print("Timestamp:", health_data.timestamp)
        print("Circuits count:", len(health_data.circuits))
        
        for name, circuit in health_data.circuits.items():
            print(f"Circuit {name}: {circuit.state} (is_open: {circuit.is_open})")
            
        print("Components found:", list(health_data.components.keys()))
        
        return True
    except Exception as e:
        print("Health check failed!")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_health())
