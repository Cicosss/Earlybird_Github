"""
Exclusion Lists Configuration
==============================

Centralized configuration for content exclusion keywords used across the bot.
This ensures consistency between GarbageFilter and ExclusionFilter.

Excluded Categories:
- Basketball and related sports
- Women's football
- American sports (NFL, etc.)
- Rugby
- Other sports (handball, volleyball, futsal, esports)

NOTE: Youth/Primavera/U19 are NOT excluded - they are RELEVANT for betting
when youth players are called up to first team or replace injured starters.
"""

# Basketball and other excluded sports
EXCLUDED_SPORTS = [
    # Basketball
    "basket",
    "basketball",
    "nba",
    "euroleague",
    "pallacanestro",
    "baloncesto",
    "koszykówka",
    "basketbol",
    "acb",
    "fiba",
    # Other sports explicitly excluded
    "tennis",
    "golf",
    "cricket",
    "hockey",
    "baseball",
    "mlb",
]

# Women's football
EXCLUDED_CATEGORIES = [
    "women",
    "woman",
    "ladies",
    "feminine",
    "femminile",
    "femenino",
    "kobiet",
    "kadın",
    "bayan",
    "wsl",
    "liga f",
    "women's",
    "womens",
    "donne",
    "féminin",
    "feminino",
    "frauen",
    "vrouwen",
    "damernas",
]

# Other excluded sports
EXCLUDED_OTHER_SPORTS = [
    # American sports
    "nfl",
    "american football",
    "super bowl",
    "touchdown",
    # Rugby
    "rugby",
    "six nations",
    "rugby union",
    "rugby league",
    # Other
    "handball",
    "volleyball",
    "futsal",
    "pallavolo",
    "balonmano",
    "beach soccer",
    "esports",
    "e-sports",
    "gaming",
]


# Helper function to get all exclusion keywords combined
def get_all_excluded_keywords() -> list[str]:
    """
    Get all exclusion keywords combined into a single list.

    Returns:
        Combined list of all exclusion keywords
    """
    return EXCLUDED_SPORTS + EXCLUDED_CATEGORIES + EXCLUDED_OTHER_SPORTS
