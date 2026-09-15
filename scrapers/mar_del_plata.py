import re
import os
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa
from captcha import CaptchaSolver
import config

class MarDelPlataScraper(BaseScraper):
    MUNICIPIO = "mar_del_plata"
    NOMBRE = "Mar del Plata"
    URL = "https://multas.mda.gob.ar/"

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.captcha_solver = CaptchaSolver()
        self.debug_dir = "debug_mar_del_plata"
        os.makedirs(self.debug_dir, exist_ok=True)

    async def _init_browser(self):
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(
            headless=config.HEADLESS,
            slow_mo=config.SLOW_MO
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.page = await self.context.new_page()

    async def _screenshot(self, name):
        try:
            await self.page.screenshot(path=f"{self.debug_dir}/{name}.png", timeout=10000)
        except Exception:
            pass

    async def _save_html(self, name):
        try:
            html = await self.page.content()
            with open(f"{self.debug_dir}/{name}.html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass

    async def _solve_captcha_if_present(self):
        html = await self.page.content()
        if "recaptcha" in html.lower() or "g-recaptcha" in html:
            site_key = None
            m = re.search(r'data-sitekey="([^"]+)"', html)
            if m:
                site_key = m.group(1)
            if site_key:
                print(f"🔑 reCAPTCHA detectado. Site key: {site_key[:20]}...")
                token = self.captcha_solver.solve_recaptcha_v2(site_key, self.URL)
                await self.page.evaluate(f"""
                    document.getElementById('g-recaptcha-response').innerHTML = '{token}';
                """)
                return True
        return False

    async def _find_and_fill(self, patente: str):
        """Intenta encontrar y completar el input de patente de múltiples formas"""
        selectors = [
            'input[name="dominio"]', 'input[name="patente"]', 'input#dominio', 'input#patente',
            'input[placeholder*="patente" i]', 'input[placeholder*="dominio" i]',
            'input[placeholder*="placa" i]', 'input[type="text"]:visible',
        ]
        for sel in selectors:
            try:
                await self.page.wait_for_selector(sel, timeout=3000)
                await self.page.fill(sel, patente.upper())
                print(f"🚗 Patente ingresada en: {sel}")
                return True
            except Exception:
                continue

        # Fallback: buscar cualquier input visible y escribir
        try:
            inputs = await self.page.query_selector_all('input:visible')
            for inp in inputs:
                input_type = await inp.get_attribute("type") or "text"
                if input_type in ["text", "search", ""]:
                    await inp.fill(patente.upper())
                    print("🚗 Patente ingresada (fallback)")
                    return True
        except Exception:
            pass

        return False

    async def _click_submit(self):
        selectors = [
            'button:has-text("Consultar")', 'input[value="Consultar"]',
            'button[type="submit"]', 'input[type="submit"]',
            '.btn-primary', '#btnConsultar', 'button:has-text("Buscar")',
        ]
        for sel in selectors:
            try:
                await self.page.click(sel, timeout=3000)
                return True
            except Exception:
                continue
        # Fallback JS
        await self.page.evaluate("""
            const btns = Array.from(document.querySelectorAll('button, input[type="submit"], a'));
            const btn = btns.find(el => /consultar|buscar|enviar/i.test(el.textContent || el.value));
            if (btn) btn.click();
        """)
        return True

    async def _extraer_infracciones(self):
        """Extracción genérica - guarda HTML para ajustar después"""
        await self.page.wait_for_timeout(4000)
        await self._screenshot("resultados")
        await self._save_html("resultados")

        text = await self.page.evaluate("() => document.body.innerText")
        html = await self.page.content()

        # Guardar HTML para debug
        with open(f"{self.debug_dir}/resultados.html", "w", encoding="utf-8") as f:
            f.write(html)

        # Verificar mensajes de "no hay infracciones"
        no_multas_phrases = [
            "no posee infracciones", "no registra infracciones", "no se encontraron",
            "sin infracciones", "no hay infracciones", "no tiene infracciones",
            "dominio no encontrado", "patente no encontrada", "no existen infracciones"
        ]
        if any(p in text.lower() for p in no_multas_phrases):
            return []

        # TODO: Ajustar selectores específicos de esta página
        # Por ahora, intentar extracción genérica
        infracciones = []

        # Buscar elementos que parezcan infracciones
        items = await self.page.query_selector_all(".card, .infraccion, .multa, .item, li, tr")
        for item in items:
            try:
                t = await item.inner_text()
                if len(t) < 20:
                    continue
                # Si parece una infracción (tiene fecha o monto)
                if re.search(r"\d{2}[/-]\d{2}[/-]\d{4}", t) or "$" in t:
                    infracciones.append(Infraccion(
                        acta="PENDIENTE",
                        motivo=t[:200].replace("\n", " "),
                        estado=EstadoActa.NO_DISPONIBLE
                    ))
            except Exception:
                continue

        return infracciones

    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        await self._init_browser()
        try:
            print(f"\n📍 Municipio: {self.MUNICIPIO}")
            print(f"🚗 Patente: {patente.upper()}")
            print("="*60)

            await self.page.goto(self.URL, wait_until="networkidle", timeout=60000)
            await self._screenshot("01_pagina_cargada")
            await self._save_html("01_pagina_cargada")

            # Resolver CAPTCHA si existe
            await self._solve_captcha_if_present()

            # Completar patente
            filled = await self._find_and_fill(patente)
            if not filled:
                raise Exception("No se pudo encontrar el campo de patente. Revisar debug/01_pagina_cargada.html")

            await self._screenshot("02_formulario_completado")

            # Enviar
            await self._click_submit()
            print("📨 Formulario enviado")
            await self.page.wait_for_timeout(5000)
            await self._screenshot("03_despues_envio")
            await self._save_html("03_despues_envio")

            # Extraer
            infracciones = await self._extraer_infracciones()

            tiene = len(infracciones) > 0
            return ResultadoConsulta(
                municipio=self.MUNICIPIO,
                patente=patente.upper(),
                tiene_infracciones=tiene,
                cantidad=len(infracciones),
                infracciones=infracciones,
                observaciones="Scraper en modo beta. Revisar archivos debug/ para ajustar selectores."
            )

        except Exception as e:
            await self._screenshot("ERROR")
            await self._save_html("ERROR")
            return ResultadoConsulta(
                municipio=self.MUNICIPIO,
                patente=patente.upper(),
                error=str(e),
                tiene_infracciones=False
            )
        finally:
            await self.close()

    async def consultar_por_dni(self, dni: str, tipo_doc: str = "DNI") -> ResultadoConsulta:
        return ResultadoConsulta(
            municipio=self.MUNICIPIO,
            dni=dni,
            error="Consulta por DNI no implementada aún",
            tiene_infracciones=False
        )

    async def close(self):
        if self.browser:
            await self.browser.close()
            print("🔒 Browser cerrado")
