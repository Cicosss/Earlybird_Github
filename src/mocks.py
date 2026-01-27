from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

@dataclass
class Match:
    id: str
    sport_key: str
    home_team: str
    away_team: str
    commence_time: str

# Mock Matches
now = datetime.now(timezone.utc)
tomorrow = now + timedelta(days=1)

MOCK_MATCHES = [
    Match(
        id="match_1",
        sport_key="soccer_brazil_serie_b",
        home_team="Santos",
        away_team="Ceara",
        commence_time=tomorrow.isoformat()
    ),
    Match(
        id="match_2",
        sport_key="soccer_turkey_super_lig",
        home_team="Galatasaray",
        away_team="Fenerbahce",
        commence_time=tomorrow.isoformat()
    )
]

# Mock Search Results
# We simulate a "High Impact" result for Santos (massive turnover) and a "Low Impact" for Galatasaray.
MOCK_SEARCH_RESULTS = {
    "match_1": [
        {
            "match_id": "match_1",
            "team": "Santos",
            "keyword": "escalação",
            "title": "Santos deve jogar com o time sub-20 contra o Ceara",
            "snippet": "O técnico decidiu poupar os titulares e o Santos vai a campo com uma equipe repleta de garotos do sub-20 devido à final da próxima semana.",
            "link": "https://globoesporte.globo.com/santos/noticia/time-reserva.html",
            "date": "1 hour ago",
            "source": "Globo Esporte"
        }
    ],
    "match_2": [
        {
            "match_id": "match_2",
            "team": "Galatasaray",
            "keyword": "kadro",
            "title": "Galatasaray tam kadro sahada",
            "snippet": "Teknik direktör derbi öncesi tüm oyuncuların hazır olduğunu belirtti. Eksik oyuncu bulunmuyor.",
            "link": "https://fanatik.com.tr/galatasaray/tam-kadro.html",
            "date": "2 hours ago",
            "source": "Fanatik"
        }
    ]
}

# Mock LLM Responses
# Keyed by team name or match_id + snippet content hash ideally, but simplified here.
MOCK_LLM_RESPONSES = {
    "Santos": {
        "relevance_score": 9,
        "category": "TURNOVER",
        "summary": "Il Santos giocherà con la squadra U20, titolari a riposo.",
        "affected_team": "Santos"
    },
    "Galatasaray": {
        "relevance_score": 2,
        "category": "OTHER",
        "summary": "Squadra al completo, nessun problema segnalato.",
        "affected_team": "Galatasaray"
    }
}
