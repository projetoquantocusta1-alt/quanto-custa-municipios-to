import re
import unicodedata


def sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def chave_nome(s: str) -> str:
    """Nome de município para comparar (sem acento, sem pontuação, sem 'D'/'DE' soltos)."""
    s = re.sub(r"[^A-Z ]", " ", sem_acento(s).replace("'", ""))
    return " ".join(p for p in s.split() if p not in {"DE", "DA", "DO", "DAS", "DOS", "D"})
