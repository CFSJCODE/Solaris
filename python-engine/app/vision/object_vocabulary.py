"""Curated local vocabulary for open-vocabulary object investigation."""

import re
import unicodedata

OBJECTS = (
    (
        "speaker",
        "caixa de som",
        (
            "caixa de som",
            "caixas de som",
            "alto-falante",
            "alto falante",
            "caixa acústica",
            "speaker",
            "loudspeaker",
            "bluetooth speaker",
            "portable speaker",
        ),
    ),
    (
        "power bank",
        "bateria externa",
        (
            "power bank",
            "powerbank",
            "portable charger",
            "carregador portátil",
            "bateria externa",
            "carregador externo",
        ),
    ),
    (
        "cabinet",
        "armário",
        (
            "cabinet",
            "armário",
            "armários",
            "gabinete",
            "storage cabinet",
        ),
    ),
    (
        "kitchen cabinet",
        "armário de cozinha",
        (
            "kitchen cabinet",
            "armário de cozinha",
            "armários de cozinha",
            "armário suspenso",
        ),
    ),
    (
        "tool cabinet",
        "armário de ferramentas",
        (
            "tool cabinet",
            "armário de ferramentas",
            "armário para ferramentas",
        ),
    ),
    ("window", "janela", ("window", "janela", "janelas")),
    ("door", "porta", ("door", "porta", "portas")),
    (
        "multimeter",
        "multímetro",
        (
            "multimeter",
            "multímetro",
            "multímetros",
            "digital multimeter",
            "multímetro digital",
        ),
    ),
    (
        "oscilloscope",
        "osciloscópio",
        (
            "oscilloscope",
            "osciloscópio",
            "osciloscópio digital",
        ),
    ),
    (
        "soldering iron",
        "ferro de solda",
        (
            "soldering iron",
            "ferro de solda",
            "estação de solda",
        ),
    ),
    ("router", "roteador", ("router", "roteador", "roteador wi-fi")),
    (
        "google nest mini",
        "Google Nest Mini",
        (
            "google nest mini",
            "nest mini",
            "google nest",
            "smart speaker",
            "caixa de som inteligente",
            "assistente de voz",
        ),
    ),
    ("lamp", "luminária", ("lamp", "luminária", "abajur")),
    ("shelf", "prateleira", ("shelf", "prateleira", "estante")),
)


def _normalize(label):
    normalized = unicodedata.normalize("NFKD", label.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^\w]+", " ", without_accents).split())


_ALIASES = {_normalize(alias): canonical for canonical, _, aliases in OBJECTS for alias in aliases}

EXTRA = tuple((canonical, label_pt) for canonical, label_pt, _ in OBJECTS)


def canonical_object_name(label: str) -> str:
    """Return a stable English class name for a known Portuguese/English alias."""
    stripped = label.strip()
    return _ALIASES.get(_normalize(stripped), stripped)
