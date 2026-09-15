import os
import time
import requests
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa
import config


class LanusScraper(BaseScraper):
    MUNICIPIO = "lanus"
    NOMBRE = "Lanus - Infratrack"
    URL_PAGE = "https://consulta-web.infratrack.com.ar/consultas.php?municipio=lanus"
    API_URL = "https://consulta-lanus.infratrack.com.ar/infracciones/a-pagar"
    SITEKEY_STATIC = "6LfjIBAaAAAAAAMu8SInR4M-_GzP3J40I1zJ2vA_"

    def __init__(self):
        self.session = requests.Session()
        self.api_key_2captcha = getattr(config, "TWOCAPTCHA_API_KEY", os.getenv("TWOCAPTCHA_API_KEY", ""))

    def _solve_captcha(self) -> str:
        if not self.api_key_2captcha:
            return ""

        url_in = "http://2captcha.com/in.php"
        payload = {
            "key": self.api_key_2captcha,
            "method": "userrecaptcha",
            "googlekey": self.SITEKEY_STATIC,
            "pageurl": self.URL_PAGE,
            "json": 1
        }
        res = self.session.post(url_in, data=payload, timeout=15).json()
        if res.get("status") != 1:
            return ""

        request_id = res.get("request")
        url_res = f"http://2captcha.com/res.php?key={self.api_key_2captcha}&action=get&id={request_id}&json=1"

        for _ in range(25):
            time.sleep(4)
            chk = self.session.get(url_res, timeout=15).json()
            if chk.get("status") == 1:
                return chk.get("request")
        return ""

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
        try:
            print(f"\nMunicipio: {self.MUNICIPIO} | Patente: {patente.upper()} (requests)")
            
            token = self._solve_captcha()
            if not token:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    error="No se pudo resolver el CAPTCHA de Lanús",
                    tiene_infracciones=False
                )

            params = {
                "tipo": "DOMINIO",
                "consulta": patente.upper(),
                "g-recaptcha-response": token,
                "sId": "null"
            }

            headers = {
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://consulta-lanus.infratrack.com.ar/"
            }

            res = self.session.get(self.API_URL, params=params, headers=headers, timeout=20)
            if res.status_code != 200:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    tiene_infracciones=False,
                    cantidad=0,
                    monto_total="$0,00",
                    infracciones=[]
                )

            data = res.json()
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

    async def consultar_por_dni(self, dni: str, tipo_doc: str = "DNI") -> ResultadoConsulta:
        return ResultadoConsulta(municipio=self.MUNICIPIO, dni=dni, error="No implementado", tiene_infracciones=False)

    async def close(self):
        pass