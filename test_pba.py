import os
import time
import requests
from datetime import datetime

# Credenciales y constantes
API_KEY_2CAPTCHA = os.getenv("TWOCAPTCHA_API_KEY", "TU_API_KEY_AQUI")  # Asegurate de poner tu key o usar env
SITEKEY_PBA = "6LfjIBAaAAAAAAMu8SInR4M-_GzP3J40I1zJ2vA_"
URL_SITIO = "https://infraccionesba.gba.gob.ar/consulta-infraccion"
API_URL = "https://infraccionesba.gba.gob.ar/rest/consultar-infraccion"

def probar_pba(patente="AB958NA"):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": URL_SITIO,
        "Origin": "https://infraccionesba.gba.gob.ar"
    }

    # 1. Hacer una petición GET inicial para obtener cookies de sesión
    print("1. Obteniendo cookies de sesión iniciales...")
    session.get(URL_SITIO, headers=headers, timeout=15)

    # 2. Resolver Captcha
    print("2. Enviando captcha a 2Captcha...")
    url_in = "http://2captcha.com/in.php"
    payload = {
        "key": API_KEY_2CAPTCHA,
        "method": "userrecaptcha",
        "googlekey": SITEKEY_PBA,
        "pageurl": URL_SITIO,
        "json": 1
    }
    res = session.post(url_in, data=payload, timeout=15).json()
    if res.get("status") != 1:
        print(f"❌ Error enviando a 2Captcha: {res}")
        return

    request_id = res.get("request")
    url_res = f"http://2captcha.com/res.php?key={API_KEY_2CAPTCHA}&action=get&id={request_id}&json=1"

    print("3. Esperando token de 2Captcha...")
    token = ""
    for _ in range(25):
        time.sleep(4)
        chk = session.get(url_res, timeout=15).json()
        if chk.get("status") == 1:
            token = chk.get("request")
            print("✅ Token obtenido exitosamente.")
            break

    if not token:
        print("❌ Timeout resolviendo captcha.")
        return

    # 3. Consultar API REST de PBA
    print("4. Consultando API REST...")
    params = {
        "dominio": patente.lower(),
        "reCaptcha": token,
        "cantPorPagina": 50,
        "paginaActual": 1
    }

    res_api = session.get(API_URL, params=params, headers=headers, timeout=20)
    print(f"Status Code: {res_api.status_code}")
    print(f"Respuesta API: {res_api.text[:300]}")

if __name__ == "__main__":
    probar_pba()