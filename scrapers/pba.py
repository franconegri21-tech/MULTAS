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
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"


class PbaScraper(BaseScraper):
    MUNICIPIO = "pba"
    NOMBRE = "Provincia de Buenos Aires"
    URL_SITIO = "https://infraccionesba.gba.gob.ar/consulta-infraccion"
    API_URL = "https://infraccionesba.gba.gob.ar/rest/consultar-infraccion"

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.api_key_2captcha = getattr(config, "TWOCAPTCHA_API_KEY", os.getenv("TWOCAPTCHA_API_KEY", ""))

    async def _init_browser(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
            ]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=self.user_agent
        )
        self.page = await self.context.new_page()

    def _resolver_recaptcha(self, sitekey: str) -> str:
        if not self.api_key_2captcha:
            print("⚠️ Advertencia: TWOCAPTCHA_API_KEY no encontrada.")
            return ""

        print(f"🔑 Enviando reCAPTCHA de PBA a 2Captcha (Sitekey: {sitekey})...")
        url_in = "http://2captcha.com/in.php"
        payload = {
            "key": self.api_key_2captcha,
            "method": "userrecaptcha",
            "googlekey": sitekey,
            "pageurl": self.URL_SITIO,
            "json": 1
        }
        res = requests.post(url_in, data=payload, timeout=15).json()
        if res.get("status") != 1:
            print(f"❌ Error al enviar reCAPTCHA a 2Captcha: {res}")
            return ""

        request_id = res.get("request")
        url_res = f"http://2captcha.com/res.php?key={self.api_key_2captcha}&action=get&id={request_id}&json=1"

        print("⏳ Esperando resolución del captcha para PBA...")
        for i in range(30):
            time.sleep(4)
            chk = requests.get(url_res, timeout=15).json()
            if chk.get("status") == 1:
                print(f"✅ reCAPTCHA de PBA resuelto en {(i+1)*4}s por 2Captcha.")
                return chk.get("request")
            elif chk.get("request") != "CAPCHA_NOT_READY":
                print(f"❌ Error devuelto por 2Captcha: {chk.get('request')}")
                break

        print("❌ Timeout esperando respuesta de 2Captcha.")
        return ""

    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        await self._init_browser()
        try:
            print(f"\nMunicipio: {self.MUNICIPIO} | Patente: {patente.upper()}")
            print(f"Navegando a {self.URL_SITIO} para extraer sitekey...")

            await self.page.goto(self.URL_SITIO, wait_until="domcontentloaded", timeout=45000)
            await self.page.wait_for_timeout(2000)

            sitekey = None
            iframe_elem = await self.page.query_selector("iframe[src*='recaptcha']")
            if iframe_elem:
                src = await iframe_elem.get_attribute("src")
                if "k=" in src:
                    sitekey = src.split("k=")[1].split("&")[0]

            if not sitekey:
                captcha_div = await self.page.query_selector("[data-sitekey], .g-recaptcha")
                if captcha_div:
                    sitekey = await captcha_div.get_attribute("data-sitekey")

            if not sitekey:
                sitekey = "6LfjIBAaAAAAAAMu8SInR4M-_GzP3J40I1zJ2vA_"

            token_recaptcha = self._resolver_recaptcha(sitekey)
            if not token_recaptcha:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    error="No se pudo resolver el captcha de PBA",
                    tiene_infracciones=False
                )

            params = {
                "dominio": patente.lower(),
                "reCaptcha": token_recaptcha,
                "cantPorPagina": 50,
                "paginaActual": 1
            }

            headers = {
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Referer": self.URL_SITIO
            }

            print("Consultando API REST de PBA con token resuelto...")
            res = requests.get(self.API_URL, params=params, headers=headers, timeout=20, verify=False)

            if res.status_code != 200:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    error=f"Error HTTP {res.status_code} al consultar la API de PBA",
                    tiene_infracciones=False
                )

            data = res.json()

            if data.get("error") or data.get("totalInfracciones", 0) == 0:
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
                fecha_str = "S/D"
                if ts_infraccion:
                    try:
                        fecha_dt = datetime.fromtimestamp(ts_infraccion / 1000.0)
                        fecha_str = fecha_dt.strftime("%d/%m/%Y")
                    except Exception:
                        pass

                detalles = item.get("infracciones", [])
                motivo_txt = "Infracción de tránsito"
                if detalles:
                    art = detalles[0].get("articulo", "")
                    desc = detalles[0].get("descripcion", "")
                    motivo_txt = f"Art. {art}: {desc}" if art else desc

                importe_neto = float(item.get("importeTotal", 0.0))
                esta_en_fecha = item.get("estaEnFecha", False)

                if esta_en_fecha:
                    importe_pleno = importe_neto * 2.0
                    monto_neto_fmt = f"${importe_neto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    monto_pleno_fmt = f"${importe_pleno:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    importe_str = f"{monto_neto_fmt} (50% Pago Voluntario) - Pleno: {monto_pleno_fmt}"
                    monto_total_acumulado += importe_neto
                else:
                    monto_neto_fmt = f"${importe_neto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
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