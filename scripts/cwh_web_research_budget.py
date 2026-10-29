"""Protect public-web reading without approving any source or extending clocks."""
from urllib.parse import urlsplit, parse_qs


def is_index_url(url):
    """Reading-order hint only; retain every discovered URL in the audit."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    query = {key.lower() for key in parse_qs(parts.query)}
    if query & {'id', 'item_id', 'docid', 'articleid', 'article_id'}:
        return False
    return parts.path.lower().rstrip('/') in {
        '', '/index.html', '/index.htm', '/index.shtml', '/index.php'}


def synthesis_reserve(available, *, integrated, has_claims):
    if not has_claims:
        return 0
    if integrated:
        # An existing raw nomination must not reserve the entire topic slice.
        # Leave most of the slice for the additional public source reading.
        return min(available, 45, max(15, available * .25))
    return min(135, available)
