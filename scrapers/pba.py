import os
import time
import urllib3
import requests
from datetime import datetime
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class PbaScraper(BaseScraper):
    MUNICIPIO = "pba"
    NOMBRE = "Provincia de Buenos Aires"
    URL_SITIO = "https://infraccionesba.gba.gob.ar/consulta-infraccion"
    API_URL = "https://infraccionesba.gba.gob.ar/rest/consultar-infraccion"

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
            "pageurl": self.URL_SITIO,
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

            await page.goto(self.URL_SITIO, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)

            sitekey = "6LfjIBAaAAAAAAMu8SInR4M-_GzP3J40I1zJ2vA_"
            iframe = await page.query_selector("iframe[src*='recaptcha']")
            if iframe:
                src = await iframe.get_attribute("src")
                if "k=" in src:
                    sitekey = src.split("k=")[1].split("&")[0]

            token_recaptcha = self._resolver_recaptcha(sitekey)
            if not token_recaptcha:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    error="No se pudo resolver el captcha de PBA",
                    tiene_infracciones=False
                )

            script_fetch = """
            async ([apiUrl, patente, token]) => {
                const url = `${apiUrl}?dominio=${patente.toLowerCase()}&reCaptcha=${token}&cantPorPagina=50&paginaActual=1`;
                const res = await fetch(url, {
                    headers: { 'Accept': 'application/json, text/plain, */*' }
                });
                return await res.json();
            }
            """
            data = await page.evaluate(script_fetch, [self.API_URL, patente, token_recaptcha])

            if not data or data.get("error") or data.get("totalInfracciones", 0) == 0:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    tiene_infracciones=False,
                    cantidad=0,
                    monto_total="$0,00",
                    infracciones=[]
                )

            actas_list = data.get("infracciones", [])
            infracciones = []
            monto_total_acumulado = 0.0

            for item in actas_list:
                nro_acta = item.get("nroActa", "S/N")
                ts_infraccion = item.get("fechaInfraccion")
                fecha_str = datetime.fromtimestamp(ts_infraccion / 1000.0).strftime("%d/%m/%Y") if ts_infraccion else "S/D"

                detalles = item.get("infracciones", [])
                motivo_txt = f"Art. {detalles[0].get('articulo', '')}: {detalles[0].get('descripcion', '')}" if detalles else "Infracción de tránsito"

                importe_neto = float(item.get("importeTotal", 0.0))
                monto_neto_fmt = f"${importe_neto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                
                # Evaluación directa sobre el objeto JSON de la infracción
                esta_en_fecha = item.get("estaEnFecha", False)
                tipo_pago = str(item.get("tipoPago", "")).upper()
                item_str = str(item).upper()

                if esta_en_fecha and ("VOLUNTARIO" in tipo_pago or "VOLUNTARIO" in item_str):
                    importe_str = f"{monto_neto_fmt} (50% Pago Voluntario)"
                else:
                    importe_str = f"{monto_neto_fmt} (Monto Pleno)"
                
                monto_total_acumulado += importe_neto

                infracciones.append(Infraccion(
                    acta=nro_acta,
                    fecha=fecha_str,
                    motivo=motivo_txt,
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
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    async def consultar_por_dni(self, dni: str, tipo_doc: str = "DNI") -> ResultadoConsulta:
        return ResultadoConsulta(municipio=self.MUNICIPIO, dni=dni, error="No implementado", tiene_infracciones=False)

    async def close(self):
        pass