import os
import time
import urllib3
import requests
from scrapers.base import BaseScraper
from models import ResultadoConsulta, Infraccion, EstadoActa
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CabaScraper(BaseScraper):
    MUNICIPIO = "caba"
    NOMBRE = "Gobierno de la Ciudad de Buenos Aires"
    URL_BASE = "https://buenosaires.gob.ar/licenciasdeconducir/consulta-de-infracciones/?actas=transito"
    SITEKEY = "6LfjIBAaAAAAAAMu8SInR4M-_GzP3J40I1zJ2vA_"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        })
        self.api_key_2captcha = getattr(config, "TWOCAPTCHA_API_KEY", os.getenv("TWOCAPTCHA_API_KEY", ""))

    def _resolver_recaptcha(self) -> str:
        if not self.api_key_2captcha:
            return ""

        url_in = "http://2captcha.com/in.php"
        payload = {
            "key": self.api_key_2captcha,
            "method": "userrecaptcha",
            "googlekey": self.SITEKEY,
            "pageurl": self.URL_BASE,
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

    async def consultar_por_patente(self, patente: str) -> ResultadoConsulta:
        try:
            print(f"\nMunicipio: {self.MUNICIPIO} | Patente: {patente.upper()} (requests)")
            
            token = self._resolver_recaptcha()
            
            payload = {
                "dominio": patente.upper(),
                "g-recaptcha-response": token,
                "op": "Consultar",
                "form_id": "consulta_infracciones_form"
            }

            res = self.session.post(self.URL_BASE, data=payload, timeout=20, verify=False)
            html = res.text

            if "sin infracciones" in html.lower() or "0 infracciones" in html.lower() or "no registra" in html.lower():
                return ResultadoConsulta(
                    municipio=self.MUNICIPIO,
                    patente=patente.upper(),
                    tiene_infracciones=False,
                    cantidad=0,
                    monto_total="$0,00",
                    infracciones=[]
                )

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("#accordionExample > .card")
            
            infracciones = []
            monto_total_acumulado = 0.0

            for c in cards:
                card_text = c.get_text(separator=" ")
                label_elem = c.select_one(".collapse-label")
                title_elem = c.select_one(".collapse-title")

                nro_acta = "S/N"
                fecha_str = "No especificada"

                if label_elem:
                    lbl = label_elem.get_text(strip=True)
                    if "Acta " in lbl:
                        clean_lbl = lbl.replace("Acta N°", "").replace("Acta ", "").strip()
                        partes = clean_lbl.split(" - ")
                        nro_acta = partes[0].strip()
                        if len(partes) > 1:
                            fecha_str = partes[1].strip()

                motivo_txt = title_elem.get_text(strip=True) if title_elem else "Infracción CABA"

                import re
                precios = re.findall(r"\$\s*[\d\.]+(?:,\d{2})?", card_text)
                importe_str = "$0,00"
                if len(precios) >= 2:
                    monto_desc = precios[1]
                    importe_str = f"{monto_desc} (50% Descuento) - Pleno: {precios[0]}"
                    try:
                        monto_total_acumulado += float(monto_desc.replace("$", "").replace(".", "").replace(",", ".").strip())
                    except Exception:
                        pass
                elif len(precios) == 1:
                    importe_str = f"{precios[0]} (Monto Pleno)"
                    try:
                        monto_total_acumulado += float(precios[0].replace("$", "").replace(".", "").replace(",", ".").strip())
                    except Exception:
                        pass

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