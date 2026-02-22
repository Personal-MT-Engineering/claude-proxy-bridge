#!/usr/bin/env python3
"""Health check utility — pings all proxies and the bridge, reports status."""

import asyncio
import sys
from pathlib import Path

# Add project root to path so we can import config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from src.config import settings


async def check_endpoint(client: httpx.AsyncClient, name: str, url: str) -> bool:
    """Check a single endpoint's health."""
    try:
        resp = await client.get(url, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "unknown")
            provider = data.get("provider", "")
            extra = f", provider: {provider}" if provider else ""
            print(f"  [OK]   {name:30s} → {url}  (status: {status}{extra})")
            return True
        else:
            print(f"  [FAIL] {name:30s} → {url}  (HTTP {resp.status_code})")
            return False
    except httpx.ConnectError:
        print(f"  [DOWN] {name:30s} → {url}  (connection refused)")
        return False
    except httpx.TimeoutException:
        print(f"  [SLOW] {name:30s} → {url}  (timeout)")
        return False
    except Exception as e:
        print(f"  [ERR]  {name:30s} → {url}  ({e})")
        return False


async def main() -> None:
    print("Claude Proxy Bridge — Health Check")
    print("=" * 70)

    endpoints = []
    for mc in settings.models:
        label = f"{mc.name.title()} ({mc.provider.key})"
        endpoints.append((label, f"http://{settings.host}:{mc.port}/health"))
    endpoints.append(("WebSocket Bridge", f"http://{settings.host}:{settings.bridge_port}/health"))

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[check_endpoint(client, name, url) for name, url in endpoints]
        )

    print("=" * 70)

    ok_count = sum(results)
    total = len(results)

    if ok_count == total:
        print(f"All {total} services are healthy!")
    else:
        print(f"{ok_count}/{total} services are healthy. {total - ok_count} service(s) down.")

    # Also check models endpoint on each proxy
    print("\nModel listings:")
    async with httpx.AsyncClient() as client:
        for mc in settings.models:
            url = f"http://{settings.host}:{mc.port}/v1/models"
            try:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {settings.api_key}"},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    print(f"  {mc.name.title():12s} ({mc.provider.key:10s}) → {models}")
                else:
                    print(f"  {mc.name.title():12s} ({mc.provider.key:10s}) → HTTP {resp.status_code}")
            except Exception as e:
                print(f"  {mc.name.title():12s} ({mc.provider.key:10s}) → Error: {e}")

    sys.exit(0 if ok_count == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
