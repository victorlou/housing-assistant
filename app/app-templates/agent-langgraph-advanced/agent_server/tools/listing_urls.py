import re


def _slugify(suburb: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", suburb.lower()).strip("-")


def build_realestate_url(suburb: str, min_rent: int, max_rent: int) -> str:
    slug = _slugify(suburb)
    return f"https://www.realestate.co.nz/residential/rental/auckland/auckland-city/{slug}"


def build_trademe_url(suburb: str, min_rent: int, max_rent: int) -> str:
    slug = _slugify(suburb).replace("-", "+")
    return (
        f"https://www.trademe.co.nz/a/property/residential/rent/search"
        f"?search_string={slug}+auckland"
        f"&price_min={min_rent}&price_max={max_rent}"
    )


def build_barfoot_url(suburb: str, min_rent: int, max_rent: int) -> str:
    slug = _slugify(suburb)
    return (
        f"https://www.barfoot.co.nz/properties/rental"
        f"/suburb={slug}/rent={min_rent}-{max_rent}"
    )
