import os
import time
import urllib3
import requests
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CabaScraper(BaseScraper):
    MUNICIPIO = "caba"
    NOMBRE = "Gobierno de la Ciudad de Buenos Aires"
    URL = "https://buenosaires.gob.ar/licenciasdeconducir/consulta-de-infracciones/?actas=transito"

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.api_key_2captcha = getattr(config, "TWOCAPTCHA_API_KEY", os.getenv("TWOCAPTCHA_API_KEY", ""))
        self.debug_dir = "debug_caba"
        os.makedirs(self.debug_dir, exist_ok=True)

    async def _init_browser(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=getattr(config, "HEADLESS", False),
            slow_mo=getattr(config, "SLOW_MO", 500),
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=self.user_agent
        )
        self.page = await self.context.new_page()

    def _resolver_recaptcha_2captcha(self, sitekey: str, page_url: str) -> str:
        if not self.api_key_2captcha:
            return ""

        url_in = "http://2captcha.com/in.php"
        payload = {
            "key": self.api_key_2captcha,
            "method": "userrecaptcha",
            "googlekey": sitekey,
            "pageurl": page_url,
            "json": 1
        }
        res = requests.post(url_in, data=payload, timeout=15).json()
        if res.get("status") != 1:
            return ""

        request_id = res.get("request")
        url_res = f"http://2captcha.com/res.php?key={self.api_key_2captcha}&action=get&id={request_id}&json=1"

        for _ in range(20):
            time.sleep(5)
            chk = requests.get(url_res, timeout=15).json()
            if chk.get("status") == 1:
                return chk.get("request")
        return ""

    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        await self._init_browser()
        try:
            print(f"\nMunicipio: {self.MUNICIPIO} | Patente: {patente.upper()}")
            await self.page.goto(self.URL, wait_until="domcontentloaded", timeout=45000)
            await self.page.wait_for_timeout(2000)

            # 1. Solapa Dominio con clic forzado
            tab_dominio = await self.page.query_selector("a[href*='dominio' i], label[for*='dominio' i], :text('Dominio'), :text('Patente')")
            if tab_dominio:
                await tab_dominio.click(force=True)
                await self.page.wait_for_timeout(1000)

            # 2. Input de patente
            input_patente = await self.page.wait_for_selector(
                "#edit-dominio, input[name='dominio']",
                state="visible",
                timeout=15000
            )
            await input_patente.fill(patente.upper())

            # 3. reCAPTCHA
            iframe_captcha = await self.page.query_selector("iframe[src*='recaptcha']")
            if iframe_captcha:
                src = await iframe_captcha.get_attribute("src")
                if "k=" in src:
                    sitekey = src.split("k=")[1].split("&")[0]
                    token = self._resolver_recaptcha_2captcha(sitekey, self.URL)
                    if token:
                        await self.page.evaluate(
                            f'document.getElementById("g-recaptcha-response").innerHTML="{token}";'
                        )

            # 4. Clic en consultar con clic forzado
            btn_consultar = await self.page.wait_for_selector(
                "button[type='submit'], input[type='submit'], button:has-text('Consultar')",
                state="visible",
                timeout=10000
            )
            await btn_consultar.click(force=True)

            try:
                await self.page.wait_for_selector(".collapse-label, .card, #accordionExample", timeout=20000)
            except Exception:
                pass

            await self.page.wait_for_timeout(4000)

            text_body = await self.page.evaluate("() => document.body.innerText")

            if "sin infracciones" in text_body.lower() or "0 infracciones" in text_body.lower() or "no registra" in text_body.lower():
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    tiene_infracciones=False,
                    cantidad=0,
                    monto_total="$0,00",
                    infracciones=[]
                )

            infracciones = []
            monto_total_acumulado = 0.0

            cards = await self.page.query_selector_all("#accordionExample > .card")

            for c in cards:
                label_elem = await c.query_selector(".collapse-label")
                title_elem = await c.query_selector(".collapse-title")

                if not label_elem or not title_elem:
                    continue

                label_text = (await label_elem.inner_text()).strip()
                title_text = (await title_elem.inner_text()).strip()
                card_text = (await c.inner_text()).replace("\n", " ")

                nro_acta = "S/N"
                fecha_str = "No especificada"

                if "Acta N°" in label_text or "Acta " in label_text:
                    clean_lbl = label_text.replace("Acta N°", "").replace("Acta ", "").strip()
                    partes = clean_lbl.split(" - ")
                    nro_acta = partes[0].strip()
                    if len(partes) > 1:
                        fecha_str = partes[1].strip()

                import re
                precios = re.findall(r"\$\s*[\d\.]+(?:,\d{2})?", card_text)

                importe_str = "$0,00"
                if len(precios) >= 2:
                    monto_pleno = precios[0]
                    monto_desc = precios[1]
                    importe_str = f"{monto_desc} (50% Descuento Aplicado) - Pleno: {monto_pleno}"
                    try:
                        val_float = float(monto_desc.replace("$", "").replace(".", "").replace(",", ".").strip())
                        monto_total_acumulado += val_float
                    except Exception:
                        pass
                elif len(precios) == 1:
                    importe_str = f"{precios[0]} (Monto Pleno)"
                    try:
                        val_float = float(precios[0].replace("$", "").replace(".", "").replace(",", ".").strip())
                        monto_total_acumulado += val_float
                    except Exception:
                        pass

                infracciones.append(Infraccion(
                    acta=nro_acta,
                    fecha=fecha_str,
                    motivo=title_text,
                    importe=importe_str,
                    estado=EstadoActa.PENDIENTE
                ))

            tiene = len(infracciones) > 0
            monto_str = f"${monto_total_acumulado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if tiene else "$0,00"

            return ResultadoConsulta(
                municipio=self.MUNICIPIO,
                patente=patente.upper(),
                tiene_infracciones=tiene,
                cantidad=len(infracciones),
                monto_total=monto_str,
                infracciones=infracciones
            )

        except Exception as e:
            return ResultadoConsulta(
                municipio=self.MUNICIPIO,
                patente=patente.upper(),
                error=str(e),
                tiene_infracciones=False
            )
        finally:
            await self.close()

    async def consultar_por_dni(self, dni: str, tipo_doc: str = "DNI") -> ResultadoConsulta:
        return ResultadoConsulta(municipio=self.MUNICIPIO, dni=dni, error="No implementado", tiene_infracciones=False)

    async def close(self):
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass