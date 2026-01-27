"""
Twitter/X Intel Accounts Configuration - EarlyBird V4.5

Account Twitter strategici per il monitoraggio via Gemini Search Grounding.
Questi account vengono interrogati all'inizio di ogni ciclo per estrarre
gli ultimi 5 post, che rimangono in cache per tutto il ciclo.

UTILIZZO:
- All'inizio di ogni ciclo: query Gemini per ultimi 5 post di ogni account
- I dati vengono cachati e usati per:
  1. Potenziare il flusso informativo per nuovi alert
  2. Confermare alert già trovati da altre fonti
  3. Arricchire il contesto decisionale

FONTE: Deep Research Gemini (Gennaio 2026)
- Round 1: Account principali (47-50)
- Round 2: Gap filling con requisiti rilassati (+23)
- Totale verificato: 49 account su 15 leghe

NOTE:
- Account ufficiali di club/leghe ESCLUSI (non insider)
- Priorità a beat writers locali e giornalisti specializzati
- Lingue multiple accettate (inglese, spagnolo, portoghese, etc.)
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum


class AccountType(Enum):
    """Tipo di account Twitter"""
    BEAT_WRITER = "beat_writer"      # Giornalista specializzato su 1-2 club
    JOURNALIST = "journalist"         # Giornalista professionista
    PODCAST = "podcast"               # Produttore podcast calcistico
    AGGREGATOR = "aggregator"         # Aggregatore notizie (non ufficiale)
    INSIDER = "insider"               # Insider con fonti dirette
    ANALYST = "analyst"               # Analista tattico/scout


class LeagueTier(Enum):
    """Tier della lega nel sistema EarlyBird"""
    ELITE_7 = "elite_7"
    TIER_2 = "tier_2"
    GLOBAL = "global"  # Account cross-league che coprono più leghe/trasferimenti internazionali


@dataclass
class TwitterIntelAccount:
    """
    Account Twitter per intel calcistico.
    
    Attributes:
        handle: Twitter handle (con @)
        name: Nome del giornalista/account
        focus: Club o lega di specializzazione
        account_type: Tipo di account
        language: Lingua principale dei tweet
        followers_approx: Follower approssimativi (K)
        note: Perché è utile per EarlyBird
    """
    handle: str
    name: str
    focus: str
    account_type: AccountType
    language: str
    followers_approx: str  # es. "156K", "5K+", "20K+"
    note: str


# ============================================
# ELITE 7 LEAGUES - TWITTER INTEL ACCOUNTS
# ============================================

TWITTER_INTEL_ELITE_7: Dict[str, List[TwitterIntelAccount]] = {
    
    # ============================================
    # 🇹🇷 TURKEY SUPER LIG (4 accounts)
    # ============================================
    "turkey": [
        TwitterIntelAccount(
            handle="@RudyGaletti",
            name="Rudy Galetti",
            focus="Galatasaray, Fenerbahçe, Super Lig",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="156K",
            note="Transfer specialist, breaking news su club turchi"
        ),
        TwitterIntelAccount(
            handle="@UEFAcomCetinCY",
            name="Cetin CY",
            focus="Calcio turco, UEFA",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="5K+",
            note="Corrispondente UEFA per Turchia, fonte credibile"
        ),
        TwitterIntelAccount(
            handle="@_sabirhan",
            name="Yağız Sabuncuoğlu",
            focus="Fenerbahçe",
            account_type=AccountType.BEAT_WRITER,
            language="turkish+english",
            followers_approx="50K+",
            note="Insider Fenerbahçe, infortuni e formazioni"
        ),
        TwitterIntelAccount(
            handle="@Onuranli",
            name="Onuranli",
            focus="Calcio turco, controversie",
            account_type=AccountType.ANALYST,
            language="turkish+english",
            followers_approx="20K+",
            note="Analisi controversie, sentiment tifosi, derby"
        ),
    ],
    
    # ============================================
    # 🇦🇷 ARGENTINA PRIMERA (4 accounts)
    # ============================================
    "argentina": [
        TwitterIntelAccount(
            handle="@BocaEnLaCopa",
            name="Boca En La Copa",
            focus="Boca Juniors - Copa Libertadores",
            account_type=AccountType.ANALYST,
            language="spanish",
            followers_approx="18.7K",
            note="Focus Copa Libertadores Boca, formazioni coppa"
        ),
        TwitterIntelAccount(
            handle="@CABJ_English",
            name="CABJ English",
            focus="Boca Juniors",
            account_type=AccountType.PODCAST,
            language="english+spanish",
            followers_approx="5K+",
            note="Podcast Boca in inglese, insider spogliatoio"
        ),
        TwitterIntelAccount(
            handle="@marc_cart",
            name="Marc Cart",
            focus="River Plate, Buenos Aires",
            account_type=AccountType.JOURNALIST,
            language="english+spanish",
            followers_approx="5K+",
            note="Giornalista Buenos Aires, copertura River Plate"
        ),
        TwitterIntelAccount(
            handle="@INDEPENDIENTEgc",
            name="Daniel Galoto",
            focus="Independiente",
            account_type=AccountType.INSIDER,
            language="spanish",
            followers_approx="22.6K",
            note="56 anni esperienza, insider storico Independiente"
        ),
    ],
    
    # ============================================
    # 🇲🇽 MEXICO LIGA MX (3 accounts)
    # ============================================
    "mexico": [
        TwitterIntelAccount(
            handle="@AllFutbolMX",
            name="All Futbol MX",
            focus="Liga MX generale",
            account_type=AccountType.AGGREGATOR,
            language="spanish+english",
            followers_approx="36K",
            note="Notizie quotidiane Liga MX, bilingue"
        ),
        TwitterIntelAccount(
            handle="@karentapia_a",
            name="Karen Tapia",
            focus="Liga MX, CDMX",
            account_type=AccountType.JOURNALIST,
            language="spanish",
            followers_approx="5K+",
            note="TV host CDMX, copertura América e Cruz Azul"
        ),
        TwitterIntelAccount(
            handle="@soymemozavala",
            name="Memo Zavala",
            focus="Liga MX",
            account_type=AccountType.JOURNALIST,
            language="spanish",
            followers_approx="5K+",
            note="Telecronista, aggiornamenti real-time partite"
        ),
    ],
    
    # ============================================
    # 🇬🇷 GREECE SUPER LEAGUE (3 accounts)
    # ============================================
    "greece": [
        TwitterIntelAccount(
            handle="@HellasFooty",
            name="Hellas Footy",
            focus="Olympiacos, Panathinaikos, AEK, PAOK",
            account_type=AccountType.PODCAST,
            language="english",
            followers_approx="15K+",
            note="Podcast settimanale, copertura Big 4 greci"
        ),
        TwitterIntelAccount(
            handle="@A_McQuarrie",
            name="A. McQuarrie",
            focus="Calcio greco, TNT Sports",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="20K+",
            note="Giornalista TNT/BBC, analisi tattica"
        ),
        TwitterIntelAccount(
            handle="@LianosKostas",
            name="Kostas Lianos",
            focus="Super League greca, internazionale",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="10K+",
            note="Sky Sports, BBC, copertura europea"
        ),
    ],
    
    # ============================================
    # 🏴󠁧󠁢󠁳󠁣󠁴󠁿 SCOTLAND PREMIERSHIP (4 accounts)
    # ============================================
    "scotland": [
        TwitterIntelAccount(
            handle="@AnthonyRJoseph",
            name="Anthony Joseph",
            focus="Calcio scozzese, Sky Sports",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="53.7K",
            note="Sky Sports News, breaking news trasferimenti"
        ),
        TwitterIntelAccount(
            handle="@anthonyabrown",
            name="Anthony Brown",
            focus="Hearts, Hibs, Edimburgo",
            account_type=AccountType.BEAT_WRITER,
            language="english",
            followers_approx="15K+",
            note="Specialista Edimburgo, autore libri Hearts"
        ),
        TwitterIntelAccount(
            handle="@alan_pattullo",
            name="Alan Pattullo",
            focus="Celtic",
            account_type=AccountType.BEAT_WRITER,
            language="english",
            followers_approx="20K+",
            note="Beat writer Celtic, formazioni e infortuni"
        ),
        TwitterIntelAccount(
            handle="@ScottBurns75",
            name="Scott Burns",
            focus="Trasferimenti scozzesi",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="25K+",
            note="Analista trasferimenti Rangers/Celtic/Aberdeen"
        ),
    ],
    
    # ============================================
    # 🇦🇺 AUSTRALIA A-LEAGUE (4 accounts)
    # ============================================
    "australia": [
        TwitterIntelAccount(
            handle="@AleagueHub",
            name="A-League Hub",
            focus="A-League generale",
            account_type=AccountType.AGGREGATOR,
            language="english",
            followers_approx="15K+",
            note="Hub centralizzato notizie A-League"
        ),
        TwitterIntelAccount(
            handle="@joeylynchy",
            name="Joey Lynch",
            focus="A-League, Melbourne",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="12.7K",
            note="ESPN/Guardian, esperto Melbourne Victory"
        ),
        TwitterIntelAccount(
            handle="@JamesDodd89",
            name="James Dodd",
            focus="A-League",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="5K+",
            note="Senior reporter Fox Sports, talk SPORT"
        ),
        TwitterIntelAccount(
            handle="@tarynheddo",
            name="Taryn Heddo",
            focus="A-League, A-League Women",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="5K+",
            note="Commentatore A-League Women, analisi partite"
        ),
    ],
    
    # ============================================
    # 🇵🇱 POLAND EKSTRAKLASA (3 accounts)
    # ============================================
    "poland": [
        TwitterIntelAccount(
            handle="@polishscout",
            name="Michał Zachodny",
            focus="Ekstraklasa, scouting",
            account_type=AccountType.ANALYST,
            language="english",
            followers_approx="30K+",
            note="Editore Ekstraklasa Magazine, giovani talenti"
        ),
        TwitterIntelAccount(
            handle="@Ryan_Hubbard",
            name="Ryan Hubbard",
            focus="Ekstraklasa",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="10K+",
            note="Contributore EKSTRAKLASAreview, copertura inglese"
        ),
        TwitterIntelAccount(
            handle="@golskapodcast",
            name="Golska Podcast",
            focus="Calcio polacco, nazionale",
            account_type=AccountType.PODCAST,
            language="english",
            followers_approx="371",
            note="Podcast inglese su Ekstraklasa, Legia vs Lech"
        ),
    ],
}


# ============================================
# TIER 2 LEAGUES - TWITTER INTEL ACCOUNTS
# ============================================

TWITTER_INTEL_TIER_2: Dict[str, List[TwitterIntelAccount]] = {
    
    # ============================================
    # 🇳🇴 NORWAY ELITESERIEN (3 accounts)
    # ============================================
    "norway": [
        TwitterIntelAccount(
            handle="@fitjar",
            name="Runa Dahl Fitjar",
            focus="Bodø/Glimt, calcio norvegese",
            account_type=AccountType.BEAT_WRITER,
            language="english",
            followers_approx="10K+",
            note="Specialista Bodø/Glimt, formazioni e tattica"
        ),
        TwitterIntelAccount(
            handle="@StianWahl",
            name="Stian Wahl",
            focus="Eliteserien, Nettavisen",
            account_type=AccountType.JOURNALIST,
            language="norwegian+english",
            followers_approx="5K+",
            note="Giornalista Nettavisen, Molde e Rosenborg"
        ),
        TwitterIntelAccount(
            handle="@ELundefugl52724",
            name="E. Lundefugl",
            focus="Molde FK",
            account_type=AccountType.INSIDER,
            language="norwegian",
            followers_approx="<1K",
            note="Molde insider, notizie allenatori e mercato"
        ),
    ],
    
    # ============================================
    # 🇫🇷 FRANCE LIGUE 1 (4 accounts)
    # ============================================
    "france": [
        TwitterIntelAccount(
            handle="@georgeboxall22",
            name="George Boxall",
            focus="Olympique Marseille",
            account_type=AccountType.BEAT_WRITER,
            language="english",
            followers_approx="20K+",
            note="Specialista OM, BBC/Guardian/FourFourTwo"
        ),
        TwitterIntelAccount(
            handle="@FrenchFtWeekly",
            name="French Football Weekly",
            focus="Ligue 1 generale",
            account_type=AccountType.PODCAST,
            language="english",
            followers_approx="17.2K",
            note="Podcast settimanale Ligue 1, analisi partite"
        ),
        TwitterIntelAccount(
            handle="@GFFN",
            name="Get French Football News",
            focus="Ligue 1, PSG, OL, OM",
            account_type=AccountType.AGGREGATOR,
            language="english",
            followers_approx="281K",
            note="Principale aggregatore Ligue 1, guida 74 pagine"
        ),
        TwitterIntelAccount(
            handle="@mattspiro",
            name="Matt Spiro",
            focus="Calcio francese",
            account_type=AccountType.PODCAST,
            language="english+french",
            followers_approx="5K+",
            note="Podcast 'Across the Channel', broadcaster"
        ),
    ],
    
    # ============================================
    # 🇧🇪 BELGIUM FIRST DIV (3 accounts)
    # ============================================
    "belgium": [
        TwitterIntelAccount(
            handle="@MarcCorneel",
            name="Marc Corneel",
            focus="Calcio belga, Mediahuis",
            account_type=AccountType.JOURNALIST,
            language="dutch+french",
            followers_approx="105+",
            note="Giornalista Mediahuis, Club Brugge/Anderlecht"
        ),
        TwitterIntelAccount(
            handle="@Purple_RSCA_",
            name="Purple RSCA",
            focus="Anderlecht",
            account_type=AccountType.AGGREGATOR,
            language="dutch+english",
            followers_approx="3.7K",
            note="Specialista Anderlecht, formazioni e infortuni"
        ),
        TwitterIntelAccount(
            handle="@GBeNeFN",
            name="GBeNeFN",
            focus="Calcio belga e olandese",
            account_type=AccountType.AGGREGATOR,
            language="english",
            followers_approx="5K+",
            note="Aggregatore Benelux, copertura multi-club"
        ),
    ],
    
    # ============================================
    # 🇦🇹 AUSTRIA BUNDESLIGA (3 accounts)
    # ============================================
    "austria": [
        TwitterIntelAccount(
            handle="@ATscoutFootball",
            name="AT Scout Football",
            focus="Bundesliga austriaca",
            account_type=AccountType.ANALYST,
            language="english",
            followers_approx="<5K",
            note="Scout Salisburgo/Rapid, analisi finanziaria"
        ),
        TwitterIntelAccount(
            handle="@austrianfooty",
            name="Austrian Footy",
            focus="Bundesliga austriaca",
            account_type=AccountType.AGGREGATOR,
            language="english",
            followers_approx="10K+",
            note="Notizie trasferimenti e infortuni Austria"
        ),
        TwitterIntelAccount(
            handle="@Sky_Johannes",
            name="Johannes (Sky Austria)",
            focus="FK Austria Wien",
            account_type=AccountType.JOURNALIST,
            language="german+english",
            followers_approx="3.8K",
            note="Reporter Sky Sport Austria, breaking news"
        ),
    ],
    
    # ============================================
    # 🇳🇱 NETHERLANDS EREDIVISIE (4 accounts)
    # ============================================
    "netherlands": [
        TwitterIntelAccount(
            handle="@EredivisieMike",
            name="Michael Statham",
            focus="Eredivisie, Ajax/PSV/Feyenoord",
            account_type=AccountType.JOURNALIST,
            language="english",
            followers_approx="3.7K",
            note="BBC/Sky/SiriusXM, esperto calcio olandese"
        ),
        TwitterIntelAccount(
            handle="@FootballOranje_",
            name="Football Oranje",
            focus="Eredivisie",
            account_type=AccountType.PODCAST,
            language="english",
            followers_approx="<5K",
            note="Podcast Eredivisie, analisi Ajax/PSV/AZ"
        ),
        TwitterIntelAccount(
            handle="@joe_baker21",
            name="Joe Baker",
            focus="Ajax, Amsterdam",
            account_type=AccountType.BEAT_WRITER,
            language="english",
            followers_approx="5K+",
            note="Scrittore Amsterdam, insider Ajax"
        ),
        TwitterIntelAccount(
            handle="@scott_redfearn",
            name="Scott Redfearn",
            focus="Eredivisie",
            account_type=AccountType.ANALYST,
            language="english",
            followers_approx="5K+",
            note="Football Oranje contributor, analisi tattica"
        ),
    ],
    
    # ============================================
    # 🇨🇳 CHINA SUPER LEAGUE (1 account) - LIMITATO
    # ============================================
    "china": [
        TwitterIntelAccount(
            handle="@titan_plus",
            name="Titan Sports",
            focus="China Super League",
            account_type=AccountType.AGGREGATOR,
            language="english+chinese",
            followers_approx="5.3K",
            note="Giornale sportivo nazionale cinese, unica fonte X viabile"
        ),
        # ⚠️ NOTA: X/Twitter non è fonte primaria per CSL
        # Raccomandazione: sistema parallelo Weibo
    ],
    
    # ============================================
    # 🇯🇵 JAPAN J-LEAGUE (3 accounts)
    # ============================================
    "japan": [
        TwitterIntelAccount(
            handle="@shogunsoccer",
            name="Ryo Nakagawara",
            focus="J-League, analisi stagione",
            account_type=AccountType.ANALYST,
            language="english",
            followers_approx="<5K",
            note="Analisi completa J-League, tattica dettagliata"
        ),
        TwitterIntelAccount(
            handle="@visselkobe_en",
            name="Vissel Kobe English",
            focus="Vissel Kobe",
            account_type=AccountType.AGGREGATOR,
            language="english",
            followers_approx="10K+",
            note="Vissel Kobe (2x campioni), formazioni e infortuni"
        ),
        TwitterIntelAccount(
            handle="@JFN_en",
            name="Japanese Football News",
            focus="J-League, nazionale",
            account_type=AccountType.AGGREGATOR,
            language="english",
            followers_approx="5K+",
            note="Traduzioni inglese notizie J-League"
        ),
    ],
    
    # ============================================
    # 🇧🇷 BRAZIL SÉRIE B (3 accounts)
    # ============================================
    "brazil_b": [
        TwitterIntelAccount(
            handle="@BrasilEdition",
            name="Brasil Edition",
            focus="Calcio brasiliano, Série B",
            account_type=AccountType.AGGREGATOR,
            language="english+portuguese",
            followers_approx="142.6K",
            note="Aggregatore calcio brasiliano, copertura Série B"
        ),
        TwitterIntelAccount(
            handle="@raphaprates",
            name="Rapha Prates",
            focus="Santos, São Paulo",
            account_type=AccountType.JOURNALIST,
            language="portuguese",
            followers_approx="19.2K",
            note="Commentatore Radio CBN, specialista Santos"
        ),
        TwitterIntelAccount(
            handle="@CABRALNETO10",
            name="Cabral Neto",
            focus="Pernambuco, Sport Recife",
            account_type=AccountType.JOURNALIST,
            language="portuguese",
            followers_approx="127.9K",
            note="Commentatore Globo/SporTV, insider Nordeste"
        ),
    ],
}


# ============================================
# GLOBAL ACCOUNTS - CROSS-LEAGUE INTEL
# ============================================
# Account che coprono trasferimenti internazionali, news globali,
# o multiple leghe. Vengono sempre inclusi nel monitoraggio h24.

TWITTER_INTEL_GLOBAL: Dict[str, List[TwitterIntelAccount]] = {
    
    # ============================================
    # 🌍 GLOBAL TRANSFER & NEWS (cross-league)
    # ============================================
    "global": [
        TwitterIntelAccount(
            handle="@oluwashina",
            name="Oluwashina",
            focus="Transfer news, African football, International",
            account_type=AccountType.INSIDER,
            language="english",
            followers_approx="10K+",
            note="Insider trasferimenti, copertura calcio africano e internazionale"
        ),
    ],
}


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_twitter_intel_accounts(league_key: str) -> List[TwitterIntelAccount]:
    """
    Ottiene gli account Twitter intel per una lega specifica.
    
    Args:
        league_key: Chiave API della lega (es. 'soccer_turkey_super_league')
        
    Returns:
        Lista di TwitterIntelAccount per la lega
    """
    # Mapping league_key -> country
    LEAGUE_TO_COUNTRY = {
        # Elite 7
        "soccer_turkey_super_league": "turkey",
        "soccer_argentina_primera_division": "argentina",
        "soccer_mexico_ligamx": "mexico",
        "soccer_greece_super_league": "greece",
        "soccer_spl": "scotland",
        "soccer_australia_aleague": "australia",
        "soccer_poland_ekstraklasa": "poland",
        # Tier 2
        "soccer_norway_eliteserien": "norway",
        "soccer_france_ligue_one": "france",
        "soccer_belgium_first_div": "belgium",
        "soccer_austria_bundesliga": "austria",
        "soccer_netherlands_eredivisie": "netherlands",
        "soccer_china_superleague": "china",
        "soccer_japan_j_league": "japan",
        "soccer_brazil_serie_b": "brazil_b",
    }
    
    country = LEAGUE_TO_COUNTRY.get(league_key)
    if not country:
        return []
    
    # Check Elite 7 first, then Tier 2
    if country in TWITTER_INTEL_ELITE_7:
        return TWITTER_INTEL_ELITE_7[country]
    elif country in TWITTER_INTEL_TIER_2:
        return TWITTER_INTEL_TIER_2[country]
    
    return []


def get_all_twitter_handles() -> List[str]:
    """
    Ottiene tutti gli handle Twitter configurati.
    
    Include: Elite 7 + Tier 2 + Global accounts.
    
    V6.2 FIX: Aggiunta validazione handle per evitare None/vuoti.
    
    Returns:
        Lista di tutti gli handle validi (con @)
    """
    handles = []
    
    for accounts in TWITTER_INTEL_ELITE_7.values():
        for a in accounts:
            # V6.2: Validazione handle - skip None/vuoti
            if a.handle and isinstance(a.handle, str) and a.handle.strip():
                handles.append(a.handle)
    
    for accounts in TWITTER_INTEL_TIER_2.values():
        for a in accounts:
            if a.handle and isinstance(a.handle, str) and a.handle.strip():
                handles.append(a.handle)
    
    # V4.6: Include Global accounts (cross-league)
    for accounts in TWITTER_INTEL_GLOBAL.values():
        for a in accounts:
            if a.handle and isinstance(a.handle, str) and a.handle.strip():
                handles.append(a.handle)
    
    return handles


def find_account_by_handle(handle: str) -> Optional[TwitterIntelAccount]:
    """
    V6.2: Funzione centralizzata per trovare un account dato l'handle.
    
    Elimina duplicazione codice in main.py e twitter_intel_cache.py.
    
    Args:
        handle: Twitter handle (con o senza @)
        
    Returns:
        TwitterIntelAccount se trovato, None altrimenti
    """
    if not handle or not isinstance(handle, str):
        return None
    
    handle_lower = handle.lower().replace("@", "").strip()
    if not handle_lower:
        return None
    
    # Search Elite 7
    for accounts in TWITTER_INTEL_ELITE_7.values():
        for acc in accounts:
            if acc.handle and acc.handle.lower().replace("@", "") == handle_lower:
                return acc
    
    # Search Tier 2
    for accounts in TWITTER_INTEL_TIER_2.values():
        for acc in accounts:
            if acc.handle and acc.handle.lower().replace("@", "") == handle_lower:
                return acc
    
    # Search Global
    for accounts in TWITTER_INTEL_GLOBAL.values():
        for acc in accounts:
            if acc.handle and acc.handle.lower().replace("@", "") == handle_lower:
                return acc
    
    return None


def get_handles_by_tier(tier: LeagueTier) -> Dict[str, List[str]]:
    """
    Ottiene gli handle raggruppati per paese, filtrati per tier.
    
    Args:
        tier: LeagueTier.ELITE_7, LeagueTier.TIER_2, o LeagueTier.GLOBAL
        
    Returns:
        Dict country -> list of handles
    """
    if tier == LeagueTier.ELITE_7:
        source = TWITTER_INTEL_ELITE_7
    elif tier == LeagueTier.TIER_2:
        source = TWITTER_INTEL_TIER_2
    elif tier == LeagueTier.GLOBAL:
        source = TWITTER_INTEL_GLOBAL
    else:
        source = TWITTER_INTEL_ELITE_7  # Default fallback
    
    return {
        country: [a.handle for a in accounts]
        for country, accounts in source.items()
    }


def get_account_count() -> Dict[str, int]:
    """
    Conta gli account per lega.
    
    Returns:
        Dict con statistiche
    """
    stats = {
        "elite_7_total": sum(len(accounts) for accounts in TWITTER_INTEL_ELITE_7.values()),
        "tier_2_total": sum(len(accounts) for accounts in TWITTER_INTEL_TIER_2.values()),
        "global_total": sum(len(accounts) for accounts in TWITTER_INTEL_GLOBAL.values()),
        "by_country": {}
    }
    
    for country, accounts in TWITTER_INTEL_ELITE_7.items():
        stats["by_country"][country] = len(accounts)
    
    for country, accounts in TWITTER_INTEL_TIER_2.items():
        stats["by_country"][country] = len(accounts)
    
    # V4.6: Include Global accounts
    for country, accounts in TWITTER_INTEL_GLOBAL.items():
        stats["by_country"][country] = len(accounts)
    
    stats["total"] = stats["elite_7_total"] + stats["tier_2_total"] + stats["global_total"]
    
    return stats


# ============================================
# GEMINI SEARCH GROUNDING PROMPT BUILDER
# ============================================

def build_gemini_twitter_extraction_prompt(handles: List[str], max_posts: int = 5) -> str:
    """
    Costruisce il prompt per Gemini Search Grounding per estrarre
    gli ultimi post dagli account Twitter specificati.
    
    Args:
        handles: Lista di handle Twitter (con @)
        max_posts: Numero massimo di post per account
        
    Returns:
        Prompt formattato per Gemini
    """
    handles_str = ", ".join(handles)
    
    prompt = f"""
Cerca su Twitter/X gli ultimi {max_posts} post di ciascuno di questi account:
{handles_str}

Per ogni account, estrai:
1. Handle dell'account
2. Data/ora del post (se disponibile)
3. Contenuto del post
4. Se menziona: infortuni, formazioni, convocati, trasferimenti

Formato output richiesto (JSON):
{{
    "accounts": [
        {{
            "handle": "@example",
            "posts": [
                {{
                    "date": "2026-01-01",
                    "content": "Testo del post...",
                    "topics": ["injury", "lineup"]
                }}
            ]
        }}
    ],
    "extraction_time": "2026-01-01T12:00:00Z"
}}

IMPORTANTE:
- Cerca SOLO post degli ultimi 7 giorni
- Ignora retweet, rispondi solo con post originali
- Se un account non ha post recenti, segnalalo con "posts": []
- Focus su contenuti calcistici (ignora post personali/off-topic)
"""
    return prompt


# ============================================
# CLI TEST
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🐦 TWITTER INTEL ACCOUNTS - EarlyBird V4.6")
    print("=" * 60)
    
    stats = get_account_count()
    print(f"\n📊 STATISTICHE:")
    print(f"   Elite 7: {stats['elite_7_total']} account")
    print(f"   Tier 2:  {stats['tier_2_total']} account")
    print(f"   Global:  {stats['global_total']} account")
    print(f"   TOTALE:  {stats['total']} account")
    
    print(f"\n📋 PER PAESE:")
    for country, count in stats["by_country"].items():
        if country in TWITTER_INTEL_ELITE_7:
            tier = "Elite 7"
        elif country in TWITTER_INTEL_TIER_2:
            tier = "Tier 2"
        else:
            tier = "Global"
        print(f"   {country}: {count} ({tier})")
    
    print(f"\n🔗 TUTTI GLI HANDLE:")
    all_handles = get_all_twitter_handles()
    print(f"   {', '.join(all_handles[:10])}...")
    print(f"   ... e altri {len(all_handles) - 10}")
