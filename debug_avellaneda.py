import asyncio
import os
from playwright.async_api import async_playwright

async def inspect_avellaneda():
    debug_dir = "debug_avellaneda"
    os.makedirs(debug_dir, exist_ok=True)
    
    async with async_playwright() as p:
        # Usamos Google Chrome instalado en el sistema para evitar las firmas de Playwright Chromium
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",  # Llama al Chrome real del sistema
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1366,768",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        
        # Eliminar banderas de automatización en JS
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        async def on_response(response):
            url = response.url
            if any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".woff", ".ico", ".svg"]):
                return
            print(f"[NET] {response.status} -> {url}")
            try:
                if "json" in response.headers.get("content-type", "") or "api" in url or "multa" in url:
                    body = await response.text()
                    print(f"   >>> [RESPUESTA API/JSON]: {body[:300]}...")
            except Exception:
                pass

        page.on("response", on_response)

        print("Navegando a https://multas.mda.gob.ar/ ...")
        await page.goto("https://multas.mda.gob.ar/", wait_until="domcontentloaded")
        
        print("\n============================================================")
        print(" INSTRUCCIONES:")
        print(" 1. Verificá si ahora sí aparece el widget de Cloudflare Turnstile.")
        print(" 2. Ingresá la patente y presioná Consultar Infracciones.")
        print(" 3. Una vez hecha la búsqueda, presioná ENTER en esta terminal.")
        print("============================================================\n")

        input("Apretá ENTER cuando hayas realizado la búsqueda...")

        await page.screenshot(path=f"{debug_dir}/02_resultado_busqueda.png")
        html = await page.content()
        with open(f"{debug_dir}/02_resultado_busqueda.html", "w", encoding="utf-8") as f:
            f.write(html)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_avellaneda())