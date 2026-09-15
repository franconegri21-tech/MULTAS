from scrapers.caba import CabaScraper
from scrapers.chaco import ChacoScraper
from scrapers.entre_rios import EntreRiosScraper
from scrapers.lanus import LanusScraper
from scrapers.mar_del_plata import MarDelPlataScraper
from scrapers.pba import PbaScraper
from scrapers.posadas import PosadasScraper
from scrapers.roque_saenz_pena import RoqueSaenzPenaScraper
from scrapers.avellaneda import AvellanedaScraper

SCRAPERS = {
    "caba": CabaScraper,
    "chaco": ChacoScraper,
    "entre_rios": EntreRiosScraper,
    "lanus": LanusScraper,
    "mar_del_plata": MarDelPlataScraper,
    "pba": PbaScraper,
    "posadas": PosadasScraper,
    "roque_saenz_pena": RoqueSaenzPenaScraper,
    "avellaneda": AvellanedaScraper,
}

def get_scraper(municipio: str):
    scraper_class = SCRAPERS.get(municipio.lower())
    if not scraper_class:
        raise ValueError(f"Municipio '{municipio}' no soportado. Disponibles: {list(SCRAPERS.keys())}")
    return scraper_class()