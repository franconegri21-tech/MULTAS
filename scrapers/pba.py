import os
import time
import urllib3
import requests
from datetime import datetime
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class PbaScraper(BaseScraper):
    MUNICIPIO = "pba"
    NOMBRE = "Provincia de Buenos Aires"
    URL_SITIO = "https://infraccionesba.gba.gob.ar/consulta-infraccion"
    API_URL = "https://infraccionesba.gba.gob.ar/rest/consultar-infraccion"
    SITEKEY_STATIC = "6LfjIBAaAAAAAAMu8SInR4M-_GzP3J40I1zJ2vA_"

    def __init__(self):
        self.session = requests.Session()
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.api_key_2captcha = getattr(config, "TWOCAPTCHA_API_KEY", os.getenv("TWOCAPTCHA_API_KEY", ""))

    def _resolver_recaptcha(self) -> str:
        if not self.api_key_2captcha:
            print("⚠️ Error: TWOCAPTCHA_API_KEY no configurada.")
            return ""

        url_in = "http://2captcha.com/in.php"
        payload = {
            "key": self.api_key_2captcha,
            "method": "userrecaptcha",
            "googlekey": self.SITEKEY_STATIC,
            "pageurl": self.URL_SITIO,
            "json": 1
        }
        res = self.session.post(url_in, data=payload, timeout=15).json()
        if res.get("status") != 1:
            print(f"❌ Error al solicitar captcha en 2Captcha: {res}")
            return ""

        request_id = res.get("request")
        url_res = f"http://2captcha.com/res.php?key={self.api_key_2captcha}&action=get&id={request_id}&json=1"

        for _ in range(25):
            time.sleep(4)
            chk = self.session.get(url_res, timeout=15).json()
            if chk.get("status") == 1:
                return chk.get("request")
        return ""

    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        try:
            print(f"\nMunicipio: {self.MUNICIPIO} | Patente: {patente.upper()} (requests)")

            # Inicializar cookies de sesión
            headers_base = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            self.session.get(self.URL_SITIO, headers=headers_base, timeout=15, verify=False)

            token_recaptcha = self._resolver_recaptcha()
            if not token_recaptcha:
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    error="No se pudo resolver el captcha de PBA (Verificar API Key de 2Captcha)",
                    tiene_infracciones=False
                )

            params = {
                "dominio": patente.lower(),
                "reCaptcha": token_recaptcha,
                "cantPorPagina": 50,
                "paginaActual": 1
            }

            headers_api = {
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Referer": self.URL_SITIO,
                "Origin": "https://infraccionesba.gba.gob.ar"
            }

            res = self.session.get(self.API_URL, params=params, headers=headers_api, timeout=20, verify=False)

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

    async def consultar_por_dni(self, dni: str, tipo_doc: str = "DNI") -> ResultadoConsulta:
        return ResultadoConsulta(municipio=self.MUNICIPIO, dni=dni, error="No implementado", tiene_infracciones=False)

    async def close(self):
        pass