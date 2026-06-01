"""Shared DOI normalization. KCI/OpenAlex return DOIs as URLs of varying form;
strip any known prefix to a bare `10.xxxx/...` DOI."""

_DOI_URL_PREFIXES = (
    "http://dx.doi.org/", "https://dx.doi.org/",
    "http://doi.org/", "https://doi.org/",
    "doi.org/", "dx.doi.org/",
)


def strip_doi_prefix(doi: str | None) -> str | None:
    if not doi:
        return None
    s = doi.strip()
    if not s:
        return None
    for prefix in _DOI_URL_PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):]
    return s
