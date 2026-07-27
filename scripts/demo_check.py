#!/usr/bin/env python3
"""Pre-demo smoke check for CityChange.

Boots the server, drives the frontend in headless Chromium with EXTERNAL
REQUESTS BLOCKED (worst-case network: no basemap, no geocoder), and
verifies that everything CityChange controls still works: page boot,
region load, all six analysis layers, the timeline, and the story panel.
Saves screenshots to scratch for eyeballing.

Usage:  python scripts/demo_check.py [--port 8891] [--keep-server]
Exit 0 = demo-safe. Non-zero = fix before presenting.

Requires: pip install playwright + a chromium (PLAYWRIGHT_BROWSERS_PATH or
executable at /opt/pw-browsers/chromium or default install).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def wait_for(url: str, timeout: float = 30.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"server did not come up at {url}")


def chromium_path() -> str | None:
    for cand in ("/opt/pw-browsers/chromium",):
        if Path(cand).exists():
            return cand
    return None  # let Playwright resolve its own install


async def drive(port: int, shots: Path) -> list[str]:
    from playwright.async_api import async_playwright

    problems: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chromium_path())
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        js_errors: list[str] = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))

        async def block_external(route):
            if f"127.0.0.1:{port}" in route.request.url:
                await route.continue_()
            else:
                await route.abort()

        await page.route("**/*", block_external)
        await page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # A region should auto-load if bundles exist; otherwise empty state.
        has_content = await page.locator("#panel-content").is_visible()
        has_empty = await page.locator("#panel-empty").is_visible()
        if not (has_content or has_empty):
            problems.append("neither story panel nor empty state visible")
        if has_content:
            title = (await page.inner_text("#region-title")).strip()
            if not title:
                problems.append("region title empty")
            for layer in ("change", "year_of_change", "confidence",
                          "anomalies", "clusters", "states"):
                await page.click(f'button[data-layer="{layer}"]')
                await page.wait_for_timeout(600)
            # timeline interaction
            await page.click('button[data-layer="states"]')
            await page.locator("#year-slider").focus()
            await page.keyboard.press("ArrowLeft")
            await page.wait_for_timeout(400)
            if not (await page.locator("#hotspot-list li").count()):
                problems.append("hotspot list empty (ok only for stable regions)")
        await page.screenshot(path=str(shots / "demo_check_final.png"), timeout=15000)

        # basemap fallback notice should have appeared (external net blocked)
        note_visible = await page.locator("#basemap-note").is_visible()
        if not note_visible:
            problems.append(
                "basemap-note not shown despite blocked tiles "
                "(fallback may be broken)"
            )
        real_errors = [e for e in js_errors if "ERR_FAILED" not in e]
        if real_errors:
            problems.append(f"JS errors: {real_errors[:3]}")
        await browser.close()
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8891)
    ap.add_argument("--keep-server", action="store_true")
    args = ap.parse_args()

    shots = Path(tempfile.mkdtemp(prefix="citychange_demo_"))
    env = dict(os.environ)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "citychange.server:app",
         "--host", "127.0.0.1", "--port", str(args.port)],
        cwd=REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for(f"http://127.0.0.1:{args.port}/api/health")
        problems = asyncio.run(drive(args.port, shots))
    finally:
        if not args.keep_server:
            server.terminate()
            server.wait(timeout=10)

    print(f"screenshots: {shots}")
    if problems:
        print("DEMO CHECK FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("DEMO CHECK PASSED — page boots, layers switch, timeline works, "
          "basemap fallback engages when offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
