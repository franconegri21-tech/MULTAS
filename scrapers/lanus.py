import os
import time
import urllib3
import requests
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LanusScraper(BaseScraper):
    MUNICIPIO = "lanus"
    NOMBRE = "Lanus - Infratrack"
    URL = "https://consulta-web.infratrack.com.ar/consultas.php?municipio=lanus"

    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.api_key_2captcha = getattr(config, "TWOCAPTCHA_API_KEY", os.getenv("TWOCAPTCHA_API_KEY", ""))

    def _resolver_recaptcha(self, sitekey: str) -> str:
        if not self.api_key_2captcha:
            return ""

        url_in = "http://2captcha.com/in.php"
        payload = {
            "key": self.api_key_2captcha,
            "method": "userrecaptcha",
            "googlekey": sitekey,
            "pageurl": self.URL,
            "enterprise": 1,
            "json": 1
        }
        res = requests.post(url_in, data=payload, timeout=15).json()
        if res.get("status") != 1:
            return ""

        request_id = res.get("request")
        url_res = f"http://2captcha.com/res.php?key={self.api_key_2captcha}&action=get&id={request_id}&json=1"

        for _ in range(35):
            time.sleep(4)
            chk = requests.get(url_res, timeout=15).json()
            if chk.get("status") == 1:
                return chk.get("request")
            elif chk.get("request") != "CAPCHA_NOT_READY":
                break
        return ""

    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        playwright = None
        browser = None
        try:
            print(f"\nMunicipio: {self.MUNICIPIO} | Patente: {patente.upper()}")
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            context = await browser.new_context(user_agent=self.user_agent)
            page = await context.new_page()

            await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)

            sitekey = "6LfjIBAaAAAAAAMu8SInR4M-_GzP3J40I1zJ2vA_"
            iframe = await page.query_selector("iframe[src*='recaptcha']")
            if iframe:
                src = await iframe.get_attribute("src")
                if "k=" in src:
                    sitekey = src.split("k=")[1].split("&")[0]

            token = self._resolver_recaptcha(sitekey)
            if not token:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    error="No se pudo resolver el CAPTCHA de Lanús",
                    tiene_infracciones=False
                )

            script_fetch = """
            async ([patente, token]) => {
                const url = `https://consulta-lanus.infratrack.com.ar/infracciones/a-pagar?tipo=DOMINIO&consulta=${patente}&g-recaptcha-response=${token}&sId=null`;
                const response = await fetch(url, {
                    headers: {
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                return await response.json();
            }
            """
            data = await page.evaluate(script_fetch, [patente.upper(), token])

            if not data or not data.get("infracciones"):
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    tiene_infracciones=False,
                    cantidad=0,
                    monto_total="$0,00",
                    infracciones=[]
                )

            infracciones_raw = data.get("infracciones", [])
            if isinstance(infracciones_raw, dict):
                infracciones_raw = list(infracciones_raw.values())

            infracciones = []
            monto_total_acumulado = 0.0

            for inf in infracciones_raw:
                acta = str(inf.get("acta", "S/N"))
                motivo = inf.get("motivo") or inf.get("descripcion") or "Infracción Lanús"
                monto = float(inf.get("monto_total_float") or inf.get("monto_float") or 0.0)
                monto_total_acumulado += monto

                infracciones.append(Infraccion(
                    acta=acta,
                    fecha=str(inf.get("fecha", "S/D")),
                    motivo=motivo,
                    importe=f"${monto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
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
                error=f"Error en Lanús: {str(e)}",
                tiene_infracciones=False
            )
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    async def consultar_por_dni(self, dni: str, tipo_doc: str = "DNI") -> ResultadoConsulta:
        return ResultadoConsulta(municipio=self.MUNICIPIO, dni=dni, error="No implementado", tiene_infracciones=False)

    async def close(self):
        pass