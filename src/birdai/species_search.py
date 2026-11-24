"""Multilingual species-name matching (English, German, French, Italian + scientific).

Matching runs against species that were actually observed in the search area,
using eBird's localized taxonomy names. It understands:

- exact names in any language:            "Eisvogel", "Martin pescatore", "Alcedo atthis"
- partial names / plurals:                "kingfishers", "red kite", "hiboux"
- German compound heads:                  "Eule" -> Waldohreule, "Meise" -> Kohlmeise
- bird groups via English family names:   "owl" -> all owls (eBird family "Owls")
- group words in all four languages:      "Eulen", "chouette", "gufo" -> Owls
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

SEARCH_LOCALES = ("en", "de", "fr", "it")


@dataclass(frozen=True)
class SpeciesNames:
    code: str
    scientific_name: str
    family: str  # English family name from eBird, e.g. "Owls"
    names: dict[str, str] = field(default_factory=dict)  # locale -> common name

    def all_names(self) -> list[str]:
        return [n for n in [*self.names.values(), self.scientific_name] if n]


@dataclass(frozen=True)
class SpeciesMatch:
    codes: list[str]
    # True when the query named a group (e.g. "owl") rather than one species
    is_group: bool
    # Query words that matched; useful to explain free-text matches
    matched_terms: list[str]


# Group words in EN/DE/FR/IT (normalized, singular and plural) -> eBird English family names.
# Family names are only available in English, so these words bridge the other languages.
_OWLS = ("Owls", "Barn-Owls")
_RAPTORS = ("Hawks, Eagles, and Kites", "Falcons and Caracaras", "Osprey")
GROUP_ALIASES: dict[str, tuple[str, ...]] = {
    **dict.fromkeys(
        ["owl", "owls", "eule", "eulen", "kauz", "kauze", "hibou", "hiboux", "chouette",
         "chouettes", "rapace nocturne", "rapaces nocturnes", "gufo", "gufi", "civetta",
         "civette", "strigiformi"], _OWLS),
    **dict.fromkeys(
        ["woodpecker", "woodpeckers", "specht", "spechte", "pic", "pics", "picchio", "picchi"],
        ("Woodpeckers",)),
    **dict.fromkeys(
        ["tit", "tits", "meise", "meisen", "mesange", "mesanges", "cincia", "cince"],
        ("Tits, Chickadees, and Titmice", "Long-tailed Tits")),
    **dict.fromkeys(
        ["duck", "ducks", "ente", "enten", "canard", "canards", "anatra", "anatre",
         "waterfowl", "wasservogel", "wasservoegel"],
        ("Ducks, Geese, and Waterfowl",)),
    **dict.fromkeys(
        ["gull", "gulls", "mowe", "mowen", "moewe", "moewen", "goeland", "goelands",
         "mouette", "mouettes", "gabbiano", "gabbiani"],
        ("Gulls, Terns, and Skimmers",)),
    **dict.fromkeys(
        ["heron", "herons", "reiher", "egret", "egrets", "airone", "aironi"],
        ("Herons, Egrets, and Bitterns",)),
    **dict.fromkeys(
        ["raptor", "raptors", "bird of prey", "birds of prey", "greifvogel", "greifvoegel",
         "rapace", "rapaces", "rapace diurne", "rapaci"], _RAPTORS),
    **dict.fromkeys(
        ["finch", "finches", "fink", "finken", "pinson", "pinsons", "fringuello", "fringuelli"],
        ("Finches, Euphonias, and Allies",)),
    **dict.fromkeys(
        ["grebe", "grebes", "taucher", "lappentaucher", "grebe huppe", "svasso", "svassi"],
        ("Grebes",)),
}

# Words that must never be treated as bird names in free text
STOPWORDS = {
    # English
    "a", "an", "and", "any", "are", "around", "at", "bird", "birds", "by", "can", "close",
    "days", "did", "for", "from", "have", "has", "in", "is", "it", "km", "last", "me",
    "near", "nearby", "of", "on", "or", "recent", "recently", "see", "seen", "show",
    "sighting", "sightings", "some", "spotted", "the", "there", "this", "to", "today",
    "week", "were", "what", "where", "which", "with", "within", "any",
    # German
    "am", "an", "auf", "bei", "beobachtet", "beobachtungen", "das", "der", "die", "ein",
    "eine", "gesehen", "gibt", "es", "im", "in", "letzte", "letzten", "nahe", "um", "und",
    "vogel", "voegel", "welche", "wo", "woche", "zeig", "zeige",
    # French
    "au", "aux", "autour", "de", "des", "du", "en", "est", "et", "il", "la", "le", "les",
    "oiseau", "oiseaux", "observe", "observes", "pres", "quels", "semaine", "un", "une", "vu", "vus", "y",
    # Italian
    "al", "alla", "ci", "dei", "della", "di", "gli", "il", "intorno", "nei", "nel",
    "osservati", "settimana", "sono", "uccelli", "uccello", "un", "una", "vicino", "visti",
}


def normalize(text: str) -> str:
    """Lowercase, strip accents (ü -> u, é -> e, ß -> ss) and split on punctuation."""
    text = text.casefold().replace("ß", "ss")
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _variants(token: str) -> set[str]:
    """The token plus simple plural stems (owls -> owl, eulen -> eule, hiboux -> hibou)."""
    out = {token}
    for suffix in ("es", "s", "en", "n", "x"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            out.add(token[: -len(suffix)])
    return out


def _token_matches(query_token: str, name_token: str) -> bool:
    for q in _variants(query_token):
        if q == name_token:
            return True
        # German compounds: "eule" matches "waldohreule", "meise" matches "kohlmeise"
        if len(q) >= 4 and name_token.endswith(q):
            return True
    return False


def _name_matches_all(query_tokens: list[str], name: str) -> bool:
    name_tokens = normalize(name).split()
    return all(any(_token_matches(q, n) for n in name_tokens) for q in query_tokens)


def _families_for(term: str) -> tuple[str, ...]:
    for variant in (term, *_variants(term)):
        if variant in GROUP_ALIASES:
            return GROUP_ALIASES[variant]
    return ()


def match_species(query: str, species: Iterable[SpeciesNames]) -> SpeciesMatch:
    """Match a species or group name (any of EN/DE/FR/IT/scientific) against species."""
    species = list(species)
    q_norm = normalize(query)
    q_tokens = [t for t in q_norm.split() if t]
    if not q_tokens:
        return SpeciesMatch([], False, [])

    # 1. Exact full name in any language -> just that species
    exact = [s.code for s in species if any(normalize(n) == q_norm for n in s.all_names())]
    if exact:
        return SpeciesMatch(exact, False, [query])

    # 2. Group word ("owl", "Eulen", "chouette") -> whole families, plus name matches
    families = _families_for(q_norm)
    if families:
        codes = [
            s.code for s in species
            if s.family in families or any(_name_matches_all(q_tokens, n) for n in s.all_names())
        ]
        return SpeciesMatch(codes, True, [query])

    # 3. Every query word appears in one of the species' names ("red kite", "kingfishers")
    codes = [s.code for s in species if any(_name_matches_all(q_tokens, n) for n in s.all_names())]
    return SpeciesMatch(codes, len(codes) > 1, [query] if codes else [])


def match_species_in_text(text: str, species: Iterable[SpeciesNames]) -> SpeciesMatch:
    """Find species mentioned anywhere in free text (used when the AI is unavailable).

    Tries each non-stopword word (and adjacent word pairs, for names like "red kite"),
    keeping the most specific matches.
    """
    species = list(species)
    words = [w for w in normalize(text).split() if w not in STOPWORDS and not w.isdigit()]
    phrases = [f"{a} {b}" for a, b in zip(words, words[1:])] + words

    best: Optional[SpeciesMatch] = None
    for phrase in phrases:
        m = match_species(phrase, species)
        if not m.codes:
            continue
        # Prefer two-word phrases, then the narrowest match
        if best is None or (len(phrase.split()), -len(m.codes)) > (
            len(best.matched_terms[0].split()), -len(best.codes)
        ):
            best = SpeciesMatch(m.codes, m.is_group, [phrase])
    return best or SpeciesMatch([], False, [])
