"""Stable verbatim source segments: models select IDs, hosts slice original text."""
import re


def source_segments(text, scope=None, scheme="line_v1"):
    # A segment ends at a sentence or line boundary; no source text is rewritten.
    if scheme not in {"line_v1", "sentence_v2"}:
        raise ValueError("Unknown source segmentation scheme")
    boundary = r"[。！？!?；;](?:[”’\"']*)"
    if scheme == "line_v1":
        boundary += r"|\n+"
    ends = [m.end() for m in re.finditer(boundary, text)]
    if not ends or ends[-1] != len(text):
        ends.append(len(text))
    result, start = [], 0
    for end in ends:
        if end > start:
            number = len(result) + 1
            result.append({"id": f"{scope}/{number}" if scope else number, "start": start, "end": end, "text": text[start:end]})
        start = end
    return result


def selected_quote(text, span, scope=None, scheme="line_v1"):
    segments = source_segments(text, scheme=scheme)
    if scope:
        if (not isinstance(span, list) or len(span) != 2
            or any(not isinstance(value, str) or not re.fullmatch(re.escape(scope) + r"/[1-9][0-9]*", value) for value in span)):
            raise ValueError("Quote segment IDs must belong to this original source")
        span = [int(value.rsplit('/', 1)[1]) for value in span]
    if (not isinstance(span, list) or len(span) != 2
        or any(type(n) is not int for n in span)
        or not 1 <= span[0] <= span[1] <= len(segments)):
        raise ValueError("quote_range must be an ordered pair of source segment IDs")
    start, end = segments[span[0] - 1]["start"], segments[span[1] - 1]["end"]
    return text[start:end], start, end
