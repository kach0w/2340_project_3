"""Location helpers for area-specific emergency alerts (custom story 2).

A document's `alert_areas` is a comma-separated list of:
  - 5-digit ZIP codes, e.g. "30332"      -> applies to that ZIP only
  - 3-digit ZIP prefixes, e.g. "303"     -> applies to every ZIP starting with 303
Blank means general guidance that applies everywhere.
"""
import re

_ZIP = re.compile(r'^(\d{5})(?:-\d{4})?$')
_AREA = re.compile(r'^\d{3}(\d{2})?$')


def normalize_zip(value):
    """Return the 5-digit ZIP for '30332' or '30332-0001', else None."""
    match = _ZIP.match((value or '').strip())
    return match.group(1) if match else None


_ZIP_IN_TEXT = re.compile(r'(?<!\d)(\d{5})(?:-\d{4})?(?!\d)')


def zip_from_location(text):
    """Pull the ZIP out of what a user typed: '30332' or a full address
    like '266 Ferst Dr NW, Atlanta, GA 30332'. Uses the last ZIP-like number,
    since street numbers come first. Returns None if there isn't one.
    """
    matches = _ZIP_IN_TEXT.findall(text or '')
    return matches[-1] if matches else None


def parse_areas(text):
    """Split an alert_areas string into clean tokens. Raises ValueError on bad ones."""
    areas, bad = [], []
    for raw in re.split(r'[,\s]+', text or ''):
        token = raw.strip()
        if not token:
            continue
        zip_code = normalize_zip(token)
        if zip_code:
            token = zip_code
        if _AREA.match(token):
            if token not in areas:
                areas.append(token)
        else:
            bad.append(raw)
    if bad:
        raise ValueError(
            f'Invalid area(s): {", ".join(bad)}. Use 5-digit ZIP codes or 3-digit ZIP prefixes.'
        )
    return areas


def area_matches(areas, zip_code):
    """True if an alert with these areas applies to zip_code.

    No areas = general guidance (applies everywhere). No zip_code = the user
    hasn't set a location, so nothing is filtered out.
    """
    if not areas or not zip_code:
        return True
    return any(zip_code.startswith(area) for area in areas)
