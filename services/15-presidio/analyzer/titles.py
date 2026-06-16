"""Known titles for absorption into name entities."""
import re

titles = {
    "akademische_titel_deutsch": [
        "Dr.",
        "Dr. med.",
        "Dr. med. dent.",
        "Dr. med. vet.",
        "Dr. rer. nat.",
        "Dr. rer. pol.",
        "Dr. rer. oec.",
        "Dr. jur.",
        "Dr. phil.",
        "Dr. theol.",
        "Dr. paed.",
        "Dr. Ing.",
        "Dr. agr.",
        "Dr. forest.",
        "Dr. rer. soc.",
        "Dr. rer. comm.",
        "Dr. rer. mont.",
        "Dr. techn.",
        "Dr. sc. hum.",
        "Dr. h.c.",
        "Dr. mult.",
        "Dr. habil.",
        "Prof.",
        "Prof. Dr.",
        "Prof. Dr. Dr.",
        "Prof. Dr. h.c.",
        "Prof. em.",
        "PD Dr.",
        "apl. Prof.",
        "Jun.-Prof.",
        "Dipl.-Ing.",
        "Dipl.-Ing. (FH)",
        "Dipl.-Kfm.",
        "Dipl.-Kff.",
        "Dipl.-Bw.",
        "Dipl.-Vw.",
        "Dipl.-Inf.",
        "Dipl.-Math.",
        "Dipl.-Phys.",
        "Dipl.-Chem.",
        "Dipl.-Biol.",
        "Dipl.-Psych.",
        "Dipl.-Päd.",
        "Dipl.-Soz.",
        "Dipl.-Jur.",
        "Dipl.-Theol.",
        "Dipl.-Geogr.",
        "Dipl.-Geol.",
        "Dipl.-Met.",
        "Dipl.-Hdl.",
        "Dipl.-Finw.",
        "Dipl.-Verww.",
        "Mag.",
        "Mag. phil.",
        "Mag. rer. nat.",
        "Mag. jur.",
        "Mag. theol.",
        "B.A.",
        "B.Sc.",
        "B.Eng.",
        "B.Ed.",
        "B.Mus.",
        "M.A.",
        "M.Sc.",
        "M.Eng.",
        "M.Ed.",
        "M.Mus.",
        "LL.B.",
        "LL.M.",
        "MBA",
        "MPA",
        "MPH",
    ],
    "akademische_titel_englisch": [
        "Ph.D.",
        "D.Phil.",
        "Ed.D.",
        "D.B.A.",
        "D.Min.",
        "D.Sc.",
        "D.Eng.",
        "D.Mus.",
        "D.Litt.",
        "Th.D.",
        "J.D.",
        "M.D.",
        "D.D.S.",
        "D.M.D.",
        "D.V.M.",
        "D.O.",
        "Pharm.D.",
        "D.P.T.",
        "O.D.",
        "D.N.P.",
        "Psy.D.",
        "Prof.",
        "Assoc. Prof.",
        "Asst. Prof.",
        "Prof. Emeritus",
        "B.A.",
        "B.Sc.",
        "B.Eng.",
        "B.Ed.",
        "B.F.A.",
        "B.Mus.",
        "B.B.A.",
        "B.Arch.",
        "B.S.N.",
        "B.Phil.",
        "B.Th.",
        "M.A.",
        "M.Sc.",
        "M.Eng.",
        "M.Ed.",
        "M.F.A.",
        "M.Mus.",
        "M.Phil.",
        "M.Res.",
        "M.Div.",
        "M.Th.",
        "M.S.W.",
        "M.P.P.",
        "LL.B.",
        "LL.M.",
        "LL.D.",
        "MBA",
        "MPA",
        "MPH",
        "MFA",
    ],
    "berufstitel_deutsch": [
        "RA",
        "RAin",
        "StB",
        "StBin",
        "WP",
        "WPin",
        "Notar",
        "Notarin",
        "Ing.",
        "Arch.",
        "Apotheker",
        "Apothekerin",
    ],
    "berufstitel_englisch": [
        "Esq.",
        "CPA",
        "CFA",
        "PE",
        "PMP",
        "CISSP",
        "CISA",
        "RN",
        "NP",
        "PA",
        "FACS",
        "FRCS",
    ],
    "anrede_und_ehrentitel_deutsch": [
        "Herr",
        "Frau",
        "Hr.",
        "Fr.",
        "Exzellenz",
        "Hochwürden",
        "Magnifizenz",
        "Spektabilität",
    ],
    "anrede_und_ehrentitel_englisch": [
        "Mr.",
        "Mrs.",
        "Ms.",
        "Miss",
        "Mx.",
        "Sir",
        "Dame",
        "Lord",
        "Lady",
        "Rev.",
        "Hon.",
        "Rt. Hon.",
    ],
    "militaer_und_staat_deutsch": [
        "Bundeskanzler",
        "Bundeskanzlerin",
        "Ministerpräsident",
        "Ministerpräsidentin",
        "Bürgermeister",
        "Bürgermeisterin",
        "Oberbürgermeister",
        "Oberbürgermeisterin",
        "Staatssekretär",
        "Staatssekretärin",
        "Botschafter",
        "Botschafterin",
        "Gen.",
        "Oberst",
        "Hptm.",
        "Maj.",
        "Lt.",
        "OLt.",
        "Fw.",
        "OFw.",
        "StFw.",
    ],
    "funktionsbezeichnungen_business": [
        "CEO",
        "CFO",
        "CTO",
        "CIO",
        "COO",
        "CMO",
        "CISO",
        "CDO",
        "CPO",
        "CLO",
        "CHRO",
        "CSO",
        "GF",
        "Vors.",
        "stv. Vors.",
    ],
    "vollmacht_und_vertretung": [
        "Ppa.",
        "i.V.",
        "i.A.",
        "gez.",
    ],
}

all_titles = [title for category in titles.values() for title in category]

# Deduplicate and sort by length descending so longer titles match first
_sorted_titles = sorted(set(all_titles), key=len, reverse=True)
_escaped = [re.escape(t) for t in _sorted_titles]

# Matches a title preceded by whitespace/start and followed by whitespace/end
TITLE_PATTERN = re.compile(
    r'(?<!\S)(' + '|'.join(_escaped) + r')(?=\s|$)',
    re.MULTILINE,
)


def find_titles(text):
    """Find all title occurrences in text. Returns [(start, end), ...]."""
    return [(m.start(1), m.end(1)) for m in TITLE_PATTERN.finditer(text)]


# Pattern anchored to start of string for strip_title
_TITLE_PREFIX_PATTERN = re.compile(
    r'^(' + '|'.join(_escaped) + r')\s*',
    re.MULTILINE,
)


def strip_title(text: str) -> str:
    """Strip leading titles from text, iteratively.

    'Dr. Max Mustermann'       → 'Max Mustermann'
    'Prof. Dr. Max Mustermann' → 'Max Mustermann'
    'Max Mustermann'           → 'Max Mustermann'
    'Dr.'                      → 'Dr.' (nothing left, keep original)
    """
    result = text
    while True:
        m = _TITLE_PREFIX_PATTERN.match(result)
        if not m:
            break
        candidate = result[m.end():]
        if not candidate.strip():
            # Stripping would leave nothing — keep as-is
            break
        result = candidate
    return result
