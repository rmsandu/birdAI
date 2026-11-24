import pytest

from birdai.species_search import SpeciesNames, match_species, match_species_in_text, normalize


def _sp(code, en, de, fr, it, sci, family):
    return SpeciesNames(code=code, scientific_name=sci, family=family,
                        names={"en": en, "de": de, "fr": fr, "it": it})


# Real eBird names (taxonomy API, locales en/de/fr/it)
SPECIES = [
    _sp("comkin1", "Common Kingfisher", "Eisvogel", "Martin-pêcheur d'Europe", "Martin pescatore", "Alcedo atthis", "Kingfishers"),
    _sp("tawowl1", "Tawny Owl", "Waldkauz", "Chouette hulotte", "Allocco", "Strix aluco", "Owls"),
    _sp("eueowl1", "Eurasian Eagle-Owl", "Uhu", "Grand-duc d'Europe", "Gufo reale", "Bubo bubo", "Owls"),
    _sp("loeowl", "Long-eared Owl", "Waldohreule", "Hibou moyen-duc", "Gufo comune", "Asio otus", "Owls"),
    _sp("barowl2", "Western Barn Owl", "Schleiereule", "Effraie des clochers", "Barbagianni", "Tyto alba", "Barn-Owls"),
    _sp("redkit1", "Red Kite", "Rotmilan", "Milan royal", "Nibbio reale", "Milvus milvus", "Hawks, Eagles, and Kites"),
    _sp("blakit1", "Black Kite", "Schwarzmilan", "Milan noir", "Nibbio bruno", "Milvus migrans", "Hawks, Eagles, and Kites"),
    _sp("comtit", "Great Tit", "Kohlmeise", "Mésange charbonnière", "Cinciallegra", "Parus major", "Tits, Chickadees, and Titmice"),
    _sp("eurbtit1", "Eurasian Blue Tit", "Blaumeise", "Mésange bleue", "Cinciarella", "Cyanistes caeruleus", "Tits, Chickadees, and Titmice"),
    _sp("mallar3", "Mallard", "Stockente", "Canard colvert", "Germano reale", "Anas platyrhynchos", "Ducks, Geese, and Waterfowl"),
    _sp("tufduc", "Tufted Duck", "Reiherente", "Fuligule morillon", "Moretta", "Aythya fuligula", "Ducks, Geese, and Waterfowl"),
    _sp("graher1", "Gray Heron", "Graureiher", "Héron cendré", "Airone cenerino", "Ardea cinerea", "Herons, Egrets, and Bitterns"),
    _sp("pipit", "Tree Pipit", "Baumpieper", "Pipit des arbres", "Prispolone", "Anthus trivialis", "Wagtails and Pipits"),
]
OWLS = {"tawowl1", "eueowl1", "loeowl", "barowl2"}


def codes(query):
    return set(match_species(query, SPECIES).codes)


def test_normalize_strips_accents_and_punctuation():
    assert normalize("Martin-pêcheur d'Europe") == "martin pecheur d europe"
    assert normalize("Zürich") == "zurich"


@pytest.mark.parametrize("query", [
    "Common Kingfisher", "kingfisher", "Kingfishers", "Eisvogel", "eisvögel",
    "Martin-pêcheur", "martin pecheur d'europe", "Martin pescatore", "Alcedo atthis",
])
def test_single_species_in_every_language(query):
    assert codes(query) == {"comkin1"}


@pytest.mark.parametrize("query", ["owl", "Owls", "Eule", "Eulen", "Kauz", "hibou", "chouettes", "gufo", "civetta"])
def test_owl_group_in_every_language(query):
    m = match_species(query, SPECIES)
    assert set(m.codes) == OWLS
    assert m.is_group


def test_multi_word_names_need_every_word():
    assert codes("red kite") == {"redkit1"}
    assert codes("kite") == {"redkit1", "blakit1"}
    assert codes("Rotmilan") == {"redkit1"}
    assert codes("Milvus") == {"redkit1", "blakit1"}  # genus


def test_german_compound_heads_and_groups():
    assert codes("Meise") == {"comtit", "eurbtit1"}
    assert codes("mésanges") == {"comtit", "eurbtit1"}
    assert codes("Reiher") == {"graher1"}  # not "Reiherente" (Tufted Duck)
    assert codes("Enten") == {"mallar3", "tufduc"}


def test_no_false_positives():
    assert codes("tit") == {"comtit", "eurbtit1"}  # not Tree Pipit
    assert codes("hoopoe") == set()
    assert codes("") == set()


@pytest.mark.parametrize("text, expected", [
    ("Any kingfishers within 25 km of Zurich this week?", {"comkin1"}),
    ("Gibt es Eulen bei Zürich?", OWLS),
    ("Avez-vous vu des chouettes près de Genève?", OWLS),
    ("Ci sono gufi vicino a Zurigo?", OWLS),
    ("Have you seen red kites near Zurich", {"redkit1"}),
])
def test_species_found_in_free_text(text, expected):
    assert set(match_species_in_text(text, SPECIES).codes) == expected


def test_free_text_without_bird_name_matches_nothing():
    assert match_species_in_text("What birds were seen near Zurich this week?", SPECIES).codes == []
