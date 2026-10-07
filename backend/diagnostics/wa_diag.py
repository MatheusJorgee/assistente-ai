"""Diagnóstico vivo do WhatsApp Web via CDP (mesmo caminho da WhatsAppTool)."""
import asyncio
import subprocess
import sys
import time

CDP_URL = "http://localhost:9222"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


async def main() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = None
        try:
            browser = await pw.chromium.connect_over_cdp(CDP_URL, timeout=4000)
            print("[1] CDP já estava de pé")
        except Exception as exc:
            print(f"[1] CDP off ({type(exc).__name__}) -> lançando Edge...")
            subprocess.Popen([
                EDGE,
                "--remote-debugging-port=9222",
                r"--user-data-dir=C:\wa_bot_profile",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            ok = False
            for i in range(15):
                await asyncio.sleep(2)
                try:
                    browser = await pw.chromium.connect_over_cdp(CDP_URL, timeout=3000)
                    ok = True
                    print(f"[1] Conectado após {2*(i+1)}s")
                    break
                except Exception:
                    pass
            if not ok:
                print("[FALHA] Não conectou ao CDP em 30s")
                return

        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = None
        for p in ctx.pages:
            if "web.whatsapp.com" in p.url:
                page = p
                break
        if not page:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print(f"[2] Abas: {[p.url[:60] for p in ctx.pages]}")
        if "web.whatsapp.com" not in page.url:
            print("[3] Navegando para web.whatsapp.com ...")
            await page.goto("https://web.whatsapp.com", timeout=60000)

        t0 = time.time()
        estado = "indefinido"
        while time.time() - t0 < 45:
            await asyncio.sleep(3)
            try:
                tem_pane = await page.locator("#pane-side").count()
                tem_canvas = await page.locator("canvas").count()
                corpo = (await page.locator("body").inner_text())[:300].replace("\n", " | ")
                if tem_pane:
                    estado = "LOGADO (lista de chats visível)"
                    break
                if tem_canvas:
                    estado = "DESLOGADO (QR code na tela)"
                    break
                print(f"    ... carregando ({int(time.time()-t0)}s) body: {corpo[:120]}")
            except Exception as exc:
                print(f"    ... erro ao inspecionar: {exc}")
        print(f"[4] ESTADO: {estado}")
        await page.screenshot(path="backend/temp_vision/wa_diag.png")
        print("[5] Screenshot: backend/temp_vision/wa_diag.png")


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
asyncio.run(main())
