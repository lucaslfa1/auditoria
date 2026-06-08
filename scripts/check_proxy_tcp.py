import asyncio
import socket
import sys

async def check_connectivity(ip, port):
    print(f"Checking connectivity to {ip}:{port}...")
    try:
        # Tenta abrir uma conexão TCP básica
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=5)
        print(f"SUCCESS: Connected to {ip}:{port}")
        writer.close()
        await writer.wait_closed()
        return True
    except Exception as e:
        print(f"FAILURE: Could not connect to {ip}:{port} - {e}")
        return False

if __name__ == "__main__":
    ip = "34.171.63.68"
    port = 28443
    asyncio.run(check_connectivity(ip, port))
