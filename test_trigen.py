import os, asyncio, httpx
from dotenv import load_dotenv

load_dotenv()

async def test_trigen():
    api_key = os.getenv("TRIGEN_API_KEY")
    print(f"API Key: {api_key[:10]}..." if api_key else "No API Key")
    
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
        "User-Agent": "ModBot/1.0"
    }
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get("https://trigen.io/api/alt/generate", headers=headers)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"Data: {data}")
                print(f"Keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                print(f"Has username: {'username' in data if isinstance(data, dict) else False}")
            else:
                print(f"Error: {r.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_trigen())
