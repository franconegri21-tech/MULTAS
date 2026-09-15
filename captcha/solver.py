import requests
import time
import config

class CaptchaSolver:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.TWOCAPTCHA_API_KEY
        self.base_url = "http://2captcha.com"

    def solve_recaptcha_v2(self, site_key: str, page_url: str, timeout: int = 120) -> str:
        if not self.api_key:
            raise ValueError("Falta TWOCAPTCHA_API_KEY en el archivo .env")

        # Enviar CAPTCHA
        payload = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "json": 1
        }

        resp = requests.post(f"{self.base_url}/in.php", data=payload, timeout=30)
        data = resp.json()

        if data.get("status") != 1:
            raise Exception(f"Error enviando CAPTCHA: {data}")

        captcha_id = data["request"]
        print(f"📤 CAPTCHA enviado a 2Captcha. ID: {captcha_id}")

        # Esperar respuesta
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(5)
            result = requests.get(
                f"{self.base_url}/res.php",
                params={"key": self.api_key, "action": "get", "id": captcha_id, "json": 1},
                timeout=30
            ).json()

            if result.get("status") == 1:
                print(f"✅ CAPTCHA resuelto en {int(time.time()-start)}s")
                return result["request"]

            if result.get("request") == "CAPCHA_NOT_READY":
                print("⏳ Aún procesando...")
                continue

            raise Exception(f"Error resolviendo CAPTCHA: {result}")

        raise TimeoutError("Timeout esperando resolución del CAPTCHA")
