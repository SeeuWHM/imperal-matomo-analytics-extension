"""
Webbee stress-tester — deploys on VPS, hammers the Matomo Analytics Connector
with realistic user prompts and logs pass/fail/error for each.

Usage:
    python test_webbee_agent.py --session <cookie_file> [--rounds N]

The script drives panel.imperal.io with Playwright (headless) using
a saved auth session (cookie JSON) so it doesn't need credentials.
"""
import asyncio
import json
import sys
import time
import argparse
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None  # type: ignore


ANALYTICS_URL = "https://panel.imperal.io/ext/analytics"
WAIT_FOR_RESPONSE_S = 30  # max seconds to wait for Webbee reply

ANALYTICS_PROMPTS = [
    "покажи трафик за вчера",
    "покажи трафик за последние 7 дней",
    "топ страниц за эту неделю",
    "откуда идет трафик",
    "сколько живых посетителей прямо сейчас",
    "какие устройства используют посетители",
    "из каких стран идет трафик",
    "есть ли аномалии в трафике",
    "сравни эту неделю с прошлой",
    "какой bounce rate",
    "покажи AI трафик — ChatGPT Perplexity",
    "трафик за прошлый месяц",
    "топ источников трафика",
    "какие страницы лучше всего работают",
    "покажи статистику за сегодня",
    "какие сайты подключены",
    "покажи конверсии за неделю",
    "новые vs возвращающиеся посетители",
]


async def get_last_message_text(page) -> str:
    """Extract the last Webbee response text from chat."""
    try:
        msgs = await page.query_selector_all("[data-testid='shell-chat'] > div > div > div")
        if msgs:
            last = msgs[-1]
            text = await last.inner_text()
            return text.strip()
    except Exception:
        pass
    return ""


async def wait_for_response(page, timeout_s: int = WAIT_FOR_RESPONSE_S) -> str:
    """Wait until Webbee stops showing 'Thinking...' and return response."""
    deadline = time.time() + timeout_s
    last_text = ""
    while time.time() < deadline:
        # Check if thinking indicator is gone
        thinking = await page.query_selector("text=Thinking...")
        if thinking is None:
            text = await get_last_message_text(page)
            if text and text != last_text:
                return text
        await asyncio.sleep(1)
    return "TIMEOUT"


async def send_prompt(page, prompt: str) -> dict:
    """Send a single prompt and wait for response."""
    t0 = time.time()
    try:
        box = await page.query_selector("textarea[placeholder='Message Webbee...']")
        if not box:
            box = await page.query_selector("input[placeholder='Message Webbee...']")
        if not box:
            return {"prompt": prompt, "status": "error", "msg": "input not found", "ms": 0}

        await box.fill(prompt)
        await box.press("Enter")
        response = await wait_for_response(page)
        elapsed_ms = int((time.time() - t0) * 1000)

        # Classify result
        lower = response.lower()
        if "timeout" in lower or response == "TIMEOUT":
            status = "timeout"
        elif any(x in lower for x in ["error", "ошибка", "не удалось", "failed", "unavailable"]):
            status = "error"
        elif any(x in lower for x in ["thinking", ""]):
            status = "empty"
        else:
            status = "ok"

        return {
            "prompt": prompt,
            "status": status,
            "response_preview": response[:200],
            "ms": elapsed_ms,
        }
    except Exception as e:
        return {"prompt": prompt, "status": "exception", "msg": str(e), "ms": 0}


async def run_extension_test(page, url: str, prompts: list[str], name: str) -> list[dict]:
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)  # let panels load

    results = []
    for i, prompt in enumerate(prompts, 1):
        print(f"[{i:2d}/{len(prompts)}] {prompt[:60]}...", end=" ", flush=True)
        result = await send_prompt(page, prompt)
        status_icon = "✅" if result["status"] == "ok" else "❌" if result["status"] == "error" else "⏳" if result["status"] == "timeout" else "⚠️"
        print(f"{status_icon} ({result['ms']}ms)")
        if result["status"] != "ok":
            preview = result.get("response_preview", result.get("msg", ""))
            print(f"        └─ {preview[:100]}")
        results.append(result)
        await asyncio.sleep(2)  # throttle

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n{name}: {ok}/{len(results)} OK")
    return results


async def main(cookie_file: str | None, rounds: int):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx_args = {}
        if cookie_file and Path(cookie_file).exists():
            with open(cookie_file) as f:
                cookies = json.load(f)
            ctx_args["storage_state"] = {"cookies": cookies, "origins": []}

        context = await browser.new_context(**ctx_args)
        page = await context.new_page()

        all_results = {"analytics": []}

        for round_n in range(1, rounds + 1):
            print(f"\n{'#'*60}")
            print(f"ROUND {round_n}/{rounds}")
            print(f"{'#'*60}")

            r_analytics = await run_extension_test(
                page, ANALYTICS_URL, ANALYTICS_PROMPTS, "Matomo Analytics Connector"
            )

            all_results["analytics"].extend(r_analytics)

        await browser.close()

        # Summary
        print("\n" + "="*60)
        print("FINAL SUMMARY")
        print("="*60)
        for ext, results in all_results.items():
            ok = sum(1 for r in results if r["status"] == "ok")
            err = sum(1 for r in results if r["status"] in ("error", "exception"))
            timeout = sum(1 for r in results if r["status"] == "timeout")
            print(f"{ext:20s}: {ok}/{len(results)} OK, {err} errors, {timeout} timeouts")

            # Show failures
            fails = [r for r in results if r["status"] != "ok"]
            if fails:
                print("  Failed prompts:")
                for f in fails[:5]:
                    print(f"  - [{f['status']}] {f['prompt'][:60]}")

        # Save results
        out = Path("webbee_test_results.json")
        out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2))
        print(f"\nResults saved to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Webbee stress tester")
    parser.add_argument("--session", help="Path to cookies JSON file", default=None)
    parser.add_argument("--rounds", type=int, default=1, help="Number of test rounds")
    args = parser.parse_args()
    asyncio.run(main(args.session, args.rounds))
