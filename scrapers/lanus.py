import re
import os
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa
from captcha import CaptchaSolver
import config


class LanusScraper(BaseScraper):
    MUNICIPIO = "lanus"
    NOMBRE = "Lanus - Infratrack"
    URL = "https://consulta-web.infratrack.com.ar/consultas.php?municipio=lanus"

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.captcha_solver = CaptchaSolver()
        self.debug_dir = "debug_lanus"
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()

    async def _get_recaptcha_sitekey(self):
        html = await self.page.content()
        m = re.search(r'data-sitekey="([^"]+)"', html)
        if m:
            return m.group(1)
        try:
            src = await self.page.get_attribute("iframe[src*='google.com/recaptcha']", "src", timeout=3000)
            m = re.search(r"k=([^&]+)", src)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None

    async def _solve_captcha(self):
        site_key = await self._get_recaptcha_sitekey()
        if not site_key:
            return None

        print(f"reCAPTCHA Lanús detectado. Site key: {site_key[:25]}...")
        try:
            token = self.captcha_solver.solve_recaptcha_v2(
                site_key=site_key,
                page_url=self.URL
            )
            return token
        except Exception as e:
            print(f"Error resolviendo CAPTCHA Lanús: {e}")
            return None

    async def _consultar_api_fetch(self, patente: str, token: str) -> dict:
        script = """
        async ([patente, token]) => {
            const baseUrl = typeof app !== 'undefined' && app.baseUrl ? app.baseUrl : 'https://consulta-lanus.infratrack.com.ar/';
            const url = `${baseUrl}infracciones/a-pagar?tipo=DOMINIO&consulta=${patente}&g-recaptcha-response=${token}&sId=null`;
            
            try {
                const response = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                if (!response.ok) {
                    return { error: true, status: response.status };
                }
                const data = await response.json();
                return { error: false, data: data };
            } catch (err) {
                return { error: true, message: err.toString() };
            }
        }
        """
        res = await self.page.evaluate(script, [patente, token])
        if res.get("error"):
            return {}
        return res.get("data", {})

    def _mapear_infraccion(self, inf: dict) -> Infraccion:
        acta = str(inf.get("acta", "S/N"))
        motivo = inf.get("motivo") or inf.get("descripcion") or inf.get("infraccion") or "Infracción de tránsito Lanús"

        monto = 0.0
        if inf.get("monto_total_float"):
            monto = float(inf["monto_total_float"])
        elif inf.get("monto_float"):
            monto = float(inf["monto_float"])
        elif inf.get("monto"):
            try:
                monto_str = str(inf["monto"]).replace("$", "").replace(".", "").replace(",", ".").strip()
                monto = float(monto_str)
            except ValueError:
                monto = 0.0

        fecha = None
        for campo in ["fecha_vencimiento", "fecha", "fecha_infraccion", "vencimiento"]:
            if inf.get(campo):
                fecha = str(inf[campo])
                break

        return Infraccion(
            acta=acta,
            fecha=fecha or "S/D",
            motivo=motivo,
            importe=f"${monto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if monto else "$0,00",
            estado=EstadoActa.PENDIENTE
        )

    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        await self._init_browser()
        try:
            print(f"\nMunicipio: {self.MUNICIPIO} | Patente: {patente.upper()}")
            await self.page.goto(self.URL, wait_until="domcontentloaded", timeout=45000)
            await self.page.wait_for_timeout(2000)

            token = await self._solve_captcha()
            if not token:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    error="No se pudo resolver el CAPTCHA de Lanús",
                    tiene_infracciones=False
                )

            data = await self._consultar_api_fetch(patente.upper(), token)

            if not data:
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

            infracciones = [self._mapear_infraccion(inf) for inf in infracciones_raw]

            tiene = len(infracciones) > 0
            monto_total_acumulado = sum(
                float(inf.importe.replace("$", "").replace(".", "").replace(",", ".")) 
                for inf in infracciones if inf.importe and "$" in inf.importe
            ) if tiene else 0.0

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