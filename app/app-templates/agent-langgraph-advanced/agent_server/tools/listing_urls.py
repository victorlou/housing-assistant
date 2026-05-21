from __future__ import annotations
from asyncio.log import logger

from dataclasses import dataclass
from difflib import get_close_matches
import re
from urllib.parse import quote, urlencode


def _normalise_key(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("ā", "a").replace("ē", "e").replace("ī", "i").replace("ō", "o").replace("ū", "u")
    value = re.sub(r"\bmt\b", "mount", value)
    value = re.sub(r"\bst\b", "saint", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalise_key(value)).strip("-")


@dataclass(frozen=True)
class SiteDecision:
    """Explains which listing sites are safe to show for a suburb."""

    realestate: str
    trademe: str
    barfoot: str


@dataclass(frozen=True)
class ListingLocation:
    """Canonical location components used by NZ property sites.

    The path-based listing URLs on realestate.co.nz and Trade Me are location
    sensitive: they expect region > district > suburb slugs. Keeping that
    structure explicit avoids accidentally forcing every suburb into Auckland.
    """

    suburb: str
    district: str
    region: str
    barfoot_supported: bool = False

    @property
    def suburb_slug(self) -> str:
        return _slugify(self.suburb)

    @property
    def district_slug(self) -> str:
        return _slugify(self.district)

    @property
    def region_slug(self) -> str:
        return _slugify(self.region)

    @property
    def display_name(self) -> str:
        return f"{self.suburb}, {self.district}, {self.region}"


# Common NZ rental-search suburbs. The URLs need realestate.co.nz / Trade Me's
# location hierarchy, not just a suburb slug. Add aliases liberally; the resolver
# normalises punctuation, macrons, and common Mt/Mount variants before lookup.
_LOCATION_ROWS: tuple[tuple[str, str, str, bool, tuple[str, ...]], ...] = (
    # Auckland — Auckland City
    ("Auckland CBD", "Auckland City", "Auckland", True, ("auckland central", "cbd", "city centre", "britomart", "wynyard quarter")),
    ("Ponsonby", "Auckland City", "Auckland", True, ()),
    ("Grey Lynn", "Auckland City", "Auckland", True, ()),
    ("Freemans Bay", "Auckland City", "Auckland", True, ()),
    ("Herne Bay", "Auckland City", "Auckland", True, ()),
    ("Westmere", "Auckland City", "Auckland", True, ()),
    ("Mount Eden", "Auckland City", "Auckland", True, ("mt eden",)),
    ("Eden Terrace", "Auckland City", "Auckland", True, ()),
    ("Epsom", "Auckland City", "Auckland", True, ()),
    ("Newmarket", "Auckland City", "Auckland", True, ()),
    ("Grafton", "Auckland City", "Auckland", True, ()),
    ("Parnell", "Auckland City", "Auckland", True, ()),
    ("Remuera", "Auckland City", "Auckland", True, ()),
    ("Onehunga", "Auckland City", "Auckland", True, ()),
    ("Sandringham", "Auckland City", "Auckland", True, ()),
    ("Kingsland", "Auckland City", "Auckland", True, ()),
    ("Mount Albert", "Auckland City", "Auckland", True, ("mt albert",)),
    ("Avondale", "Auckland City", "Auckland", True, ()),
    ("Point Chevalier", "Auckland City", "Auckland", True, ("pt chevalier",)),
    ("Mount Roskill", "Auckland City", "Auckland", True, ("mt roskill",)),
    ("Three Kings", "Auckland City", "Auckland", True, ()),
    ("Balmoral", "Auckland City", "Auckland", True, ()),
    ("Greenlane", "Auckland City", "Auckland", True, ()),
    ("Ellerslie", "Auckland City", "Auckland", True, ()),
    ("Orakei", "Auckland City", "Auckland", True, ("Ōrākei",)),
    ("Mission Bay", "Auckland City", "Auckland", True, ()),
    ("Kohimarama", "Auckland City", "Auckland", True, ()),
    ("Saint Heliers", "Auckland City", "Auckland", True, ("st heliers",)),
    # Auckland — former councils/districts used by listing sites
    ("Takapuna", "North Shore City", "Auckland", True, ()),
    ("Devonport", "North Shore City", "Auckland", True, ()),
    ("Milford", "North Shore City", "Auckland", True, ()),
    ("Glenfield", "North Shore City", "Auckland", True, ()),
    ("Birkenhead", "North Shore City", "Auckland", True, ()),
    ("Northcote", "North Shore City", "Auckland", True, ()),
    ("Albany", "North Shore City", "Auckland", True, ()),
    ("Browns Bay", "North Shore City", "Auckland", True, ()),
    ("Henderson", "Waitakere City", "Auckland", True, ()),
    ("New Lynn", "Waitakere City", "Auckland", True, ()),
    ("Glen Eden", "Waitakere City", "Auckland", True, ()),
    ("Titirangi", "Waitakere City", "Auckland", True, ()),
    ("Te Atatu Peninsula", "Waitakere City", "Auckland", True, ("te atatū peninsula",)),
    ("Te Atatu South", "Waitakere City", "Auckland", True, ("te atatū south",)),
    ("Hobsonville", "Waitakere City", "Auckland", True, ()),
    ("Massey", "Waitakere City", "Auckland", True, ()),
    ("Ranui", "Waitakere City", "Auckland", True, ()),
    ("Manukau", "Manukau City", "Auckland", True, ("manukau city",)),
    ("Mangere", "Manukau City", "Auckland", True, ("māngere",)),
    ("Otahuhu", "Manukau City", "Auckland", True, ("ōtāhuhu",)),
    ("Papatoetoe", "Manukau City", "Auckland", True, ()),
    ("Flat Bush", "Manukau City", "Auckland", True, ()),
    ("Howick", "Manukau City", "Auckland", True, ()),
    ("Botany Downs", "Manukau City", "Auckland", True, ()),
    ("Pakuranga", "Manukau City", "Auckland", True, ()),
    ("East Tamaki", "Manukau City", "Auckland", True, ("east tāmaki",)),
    ("Otara", "Manukau City", "Auckland", True, ("ōtara",)),
    ("Papakura", "Papakura", "Auckland", True, ()),
    ("Pukekohe", "Franklin", "Auckland", True, ()),
    ("Orewa", "Rodney", "Auckland", True, ("ōrewa",)),
    # Wellington region
    ("Te Aro", "Wellington City", "Wellington", False, ()),
    ("Mount Cook", "Wellington City", "Wellington", False, ("mt cook",)),
    ("Newtown", "Wellington City", "Wellington", False, ()),
    ("Brooklyn", "Wellington City", "Wellington", False, ()),
    ("Kelburn", "Wellington City", "Wellington", False, ()),
    ("Thorndon", "Wellington City", "Wellington", False, ()),
    ("Karori", "Wellington City", "Wellington", False, ()),
    ("Island Bay", "Wellington City", "Wellington", False, ()),
    ("Johnsonville", "Wellington City", "Wellington", False, ()),
    ("Miramar", "Wellington City", "Wellington", False, ()),
    ("Kilbirnie", "Wellington City", "Wellington", False, ()),
    ("Oriental Bay", "Wellington City", "Wellington", False, ()),
    ("Mount Victoria", "Wellington City", "Wellington", False, ("mt victoria",)),
    ("Hataitai", "Wellington City", "Wellington", False, ()),
    ("Wadestown", "Wellington City", "Wellington", False, ()),
    ("Petone", "Lower Hutt", "Wellington", False, ()),
    ("Lower Hutt", "Lower Hutt", "Wellington", False, ()),
    ("Wainuiomata", "Lower Hutt", "Wellington", False, ()),
    ("Upper Hutt", "Upper Hutt", "Wellington", False, ()),
    ("Porirua", "Porirua", "Wellington", False, ()),
    ("Paraparaumu", "Kapiti Coast", "Wellington", False, ("kāpiti",)),
    # Christchurch / Canterbury
    ("Christchurch Central", "Christchurch City", "Canterbury", False, ("christchurch cbd", "christchurch city centre")),
    ("Riccarton", "Christchurch City", "Canterbury", False, ()),
    ("Addington", "Christchurch City", "Canterbury", False, ()),
    ("Sydenham", "Christchurch City", "Canterbury", False, ()),
    ("Merivale", "Christchurch City", "Canterbury", False, ()),
    ("Papanui", "Christchurch City", "Canterbury", False, ()),
    ("Hornby", "Christchurch City", "Canterbury", False, ()),
    ("Linwood", "Christchurch City", "Canterbury", False, ()),
    ("Spreydon", "Christchurch City", "Canterbury", False, ()),
    # Other common centres
    ("Hamilton Central", "Hamilton City", "Waikato", False, ("hamilton cbd",)),
    ("Hillcrest", "Hamilton City", "Waikato", False, ()),
    ("Tauranga", "Tauranga", "Bay of Plenty", True, ()),
    ("Mount Maunganui", "Tauranga", "Bay of Plenty", True, ("mt maunganui",)),
    ("Papamoa", "Tauranga", "Bay of Plenty", True, ("pāpāmoa",)),
    ("Whakatane", "Whakatane", "Bay of Plenty", True, ("whakatāne",)),
    ("Rotorua", "Rotorua", "Bay of Plenty", True, ()),
    ("Whangarei", "Whangarei", "Northland", True, ("whangārei",)),
    ("Kerikeri", "Far North", "Northland", True, ()),
    ("Kaitaia", "Far North", "Northland", True, ()),
    ("Dunedin Central", "Dunedin City", "Otago", False, ("dunedin cbd",)),
    ("North Dunedin", "Dunedin City", "Otago", False, ()),
)

_LOCATION_INDEX: dict[str, ListingLocation] = {}
for _suburb, _district, _region, _barfoot_supported, _aliases in _LOCATION_ROWS:
    _location = ListingLocation(_suburb, _district, _region, _barfoot_supported)
    for _name in (_suburb, *_aliases):
        _LOCATION_INDEX[_normalise_key(_name)] = _location

_LOCATION_KEYS_BY_LENGTH: list[str] = sorted(_LOCATION_INDEX.keys(), key=lambda value: len(value), reverse=True)
_AREA_QUALIFIER_PATTERN = re.compile(
    r"\b(?:north|south|east|west|central|north east|north west|south east|south west|inner|outer|urban|rural)\b$"
)


_DISTRICT_REGION_HINTS: tuple[tuple[str, str], ...] = (
    ("auckland city", "Auckland"),
    ("north shore city", "Auckland"),
    ("waitakere city", "Auckland"),
    ("manukau city", "Auckland"),
    ("papakura", "Auckland"),
    ("franklin", "Auckland"),
    ("rodney", "Auckland"),
    ("wellington city", "Wellington"),
    ("lower hutt", "Wellington"),
    ("upper hutt", "Wellington"),
    ("porirua", "Wellington"),
    ("kapiti coast", "Wellington"),
    ("christchurch city", "Canterbury"),
    ("hamilton city", "Waikato"),
    ("tauranga", "Bay of Plenty"),
    ("dunedin city", "Otago"),
)


def _clean_suburb_input(suburb: str) -> str:
    return re.sub(r"\s+", " ", suburb.replace("/", " ").replace(",", " ")).strip()


def _strip_area_qualifiers(key: str) -> str:
    """Convert SA2-style names like 'onehunga north east' to 'onehunga'."""

    previous = None
    stripped = key
    while previous != stripped:
        previous = stripped
        stripped = _AREA_QUALIFIER_PATTERN.sub("", stripped).strip()
    return stripped


def _resolve_from_key(key: str) -> ListingLocation | None:
    if key in _LOCATION_INDEX:
        return _LOCATION_INDEX[key]

    stripped_key = _strip_area_qualifiers(key)
    if stripped_key in _LOCATION_INDEX:
        return _LOCATION_INDEX[stripped_key]

    # Catch dataset/SA2 variants such as "mt eden south", "ponsonby west", or
    # "new lynn central" without needing every micro-area in the mapping table.
    for candidate_key in _LOCATION_KEYS_BY_LENGTH:
        if key.startswith(f"{candidate_key} "):
            remainder = key[len(candidate_key) :].strip()
            if _strip_area_qualifiers(remainder) == "":
                return _LOCATION_INDEX[candidate_key]

    # Last resort: tolerate small typos only when there is a strong single match.
    matches = get_close_matches(stripped_key or key, _LOCATION_KEYS_BY_LENGTH, n=1, cutoff=0.9)
    if matches:
        return _LOCATION_INDEX[matches[0]]

    return None


def resolve_listing_location(suburb: str) -> ListingLocation | None:
    """Resolve a user-provided suburb to region > district > suburb.

    Returns None for unknown/ambiguous locations so callers can fall back to a
    broad site search instead of emitting a misleading Auckland-specific path.
    """

    clean = _clean_suburb_input(suburb)
    key = _normalise_key(clean)

    if location := _resolve_from_key(key):
        return location

    # Handle inputs like "Te Aro Wellington" or "Ponsonby Auckland" by stripping
    # a trailing region/district hint, then resolving the suburb itself.
    location_hints = {region for _, _, region, _, _ in _LOCATION_ROWS}
    location_hints.update(district for _, district, _, _, _ in _LOCATION_ROWS)
    for hint in sorted((_normalise_key(value) for value in location_hints), key=len, reverse=True):
        if key.endswith(f" {hint}"):
            suburb_key = key[: -len(hint)].strip()
            if location := _resolve_from_key(suburb_key):
                return location

    return None


def _title_from_key(value: str) -> str:
    small_words = {"of", "the", "and"}
    words = []
    for word in value.split():
        if word in small_words:
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _fallback_query(suburb: str, location: ListingLocation | None = None) -> str:
    if location:
        return f"{location.suburb} {location.district} {location.region}"
    return _clean_suburb_input(suburb)


def build_realestate_url(suburb: str, min_rent: int, max_rent: int) -> str:
    """Build the realestate.co.nz link.

    Decision rule: realestate.co.nz is predictable for exact region > district >
    suburb paths, so we show one Realestate link only. For unknown locations we
    use their broad rental search rather than inventing a path.
    """

    location = resolve_listing_location(suburb)
    if location:
        return (
            "https://www.realestate.co.nz/residential/rental/"
            f"{location.region_slug}/{location.district_slug}/{location.suburb_slug}"
        )

    return (
        "https://www.realestate.co.nz/residential/rental"
        f"?{urlencode({'search': _fallback_query(suburb)})}"
    )


def build_trademe_location_url(suburb: str, min_rent: int, max_rent: int) -> str | None:
    location = resolve_listing_location(suburb)
    if not location:
        return None

    return (
        "https://www.trademe.co.nz/a/property/residential/rent/"
        f"{location.region_slug}/{location.district_slug}/{location.suburb_slug}/search"
        f"?{urlencode({'price_min': min_rent, 'price_max': max_rent})}"
    )


def build_trademe_keyword_url(suburb: str, min_rent: int, max_rent: int) -> str:
    location = resolve_listing_location(suburb)
    search_string = location.suburb if location else _clean_suburb_input(suburb)
    return (
        "https://www.trademe.co.nz/a/property/residential/rent/search"
        f"?{urlencode({'search_string': search_string, 'price_min': min_rent, 'price_max': max_rent}, quote_via=quote)}"
    )


def build_trademe_url(suburb: str, min_rent: int, max_rent: int) -> str:
    """Backwards-compatible primary Trade Me URL.

    Decision rule: Trade Me can be inconsistent across structured location URLs,
    so the frontend receives two choices when we have a resolved location:
    location search and keyword search. This function returns the location URL
    as the primary URL when available, otherwise keyword search.
    """

    return build_trademe_location_url(suburb, min_rent, max_rent) or build_trademe_keyword_url(suburb, min_rent, max_rent)


def _barfoot_suburb_slug(location: ListingLocation) -> str:
    if location.region == "Bay of Plenty":
        return f"{location.suburb_slug}-bay"
    if location.region == "Northland":
        return f"{location.suburb_slug}-northland"
    return location.suburb_slug


def build_barfoot_url(suburb: str, min_rent: int, max_rent: int) -> str | None:
    """Build Barfoot link only for regions where Barfoot has rental inventory.

    Decision rule: show Barfoot only for supported markets (currently Auckland,
    Bay of Plenty, and Northland rows in the resolver). Return None elsewhere so
    the frontend skips the Barfoot button.
    """

    location = resolve_listing_location(suburb)
    if not location or not location.barfoot_supported:
        return None

    base_url = "https://www.barfoot.co.nz/properties/rental"
    suburb_segment = f"suburb={_barfoot_suburb_slug(location)}"
    rent_segment = f"rent={min_rent}-{max_rent}"

    if location.region == "Auckland":
        return f"{base_url}/region=auckland-city/{suburb_segment}/{rent_segment}"

    # Barfoot & Thompson also has a smaller rental footprint in Bay of Plenty and
    # Northland. Those URLs use path filters too, but without the Auckland region
    # segment, e.g. /suburb=tauranga-bay/rent=300-700.
    return f"{base_url}/{suburb_segment}/{rent_segment}"


def _site_decision(location: ListingLocation | None) -> SiteDecision:
    if not location:
        return SiteDecision(
            realestate="show broad rental search because exact region/district/suburb is unknown",
            trademe="show keyword search only because exact location confidence is low",
            barfoot="skip because Barfoot region support is unknown",
        )

    return SiteDecision(
        realestate="show exact region/district/suburb path",
        trademe="show both location search and keyword search so the user can choose",
        barfoot=(
            "show Barfoot path-filter URL"
            if location.barfoot_supported
            else "skip because Barfoot supports Auckland, Bay of Plenty, and Northland only"
        ),
    )


def build_listing_urls(suburb: str, min_rent: int, max_rent: int) -> dict[str, str | dict[str, str | bool] | None]:

    logger.info(f"Building listing URLs for suburb='{suburb}', min_rent={min_rent}, max_rent={max_rent}")
    
    location = resolve_listing_location(suburb)@
    decision = _site_decision(location)
    return {
        "suburb": location.display_name if location else _clean_suburb_input(suburb),
        # Site showcase workflow:
        # 1. Realestate: always one link. Exact path when resolved; broad search otherwise.
        # 2. Trade Me: exact location + keyword when resolved; keyword-only when unresolved.
        # 3. Barfoot: show only where Barfoot has meaningful regional rental coverage.
        "realestate": build_realestate_url(suburb, min_rent, max_rent),
        "trademe": build_trademe_url(suburb, min_rent, max_rent),
        "trademe_location": build_trademe_location_url(suburb, min_rent, max_rent),
        "trademe_keyword": build_trademe_keyword_url(suburb, min_rent, max_rent),
        "barfoot": build_barfoot_url(suburb, min_rent, max_rent),
        "site_decision": {
            "realestate": decision.realestate,
            "trademe": decision.trademe,
            "barfoot": decision.barfoot,
        },
        "resolved_location": (
            {
                "suburb": location.suburb,
                "district": location.district,
                "region": location.region,
                "barfoot_supported": location.barfoot_supported,
            }
            if location
            else None
        ),
    }
