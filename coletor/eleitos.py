"""Prefeitos, vices e vereadores eleitos (TSE — dados abertos). Filtrado pelo estado de config.UF.

consulta_cand_AAAA.zip -> consulta_cand_AAAA_CE.csv (latin-1, ';')
bem_candidato_AAAA.zip -> bem_candidato_AAAA_CE.csv
"""
import csv
import io
import zipfile

from coletor.texto import sem_acento

CARGO_PREFEITO, CARGO_VICE, CARGO_VEREADOR = "11", "12", "13"
ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MEDIA"}


def _csv_do_zip(conteudo: bytes, uf: str):
    z = zipfile.ZipFile(io.BytesIO(conteudo))
    nome = next((n for n in z.namelist() if n.upper().endswith(f"_{uf}.CSV")), None)
    if nome is None:
        raise ValueError(f"arquivo do {uf} não encontrado no zip ({z.namelist()[:5]}...)")
    texto = z.read(nome).decode("latin-1")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def _valor(s: str) -> float:
    s = (s or "").strip()
    if not s or s.startswith("#"):
        return 0.0
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def bens_por_candidato(conteudo_zip: bytes, uf: str = "CE") -> dict[str, float]:
    out: dict[str, float] = {}
    for r in _csv_do_zip(conteudo_zip, uf):
        sq = (r.get("SQ_CANDIDATO") or "").strip()
        if sq:
            out[sq] = round(out.get(sq, 0.0) + _valor(r.get("VR_BEM_CANDIDATO")), 2)
    return out


def _pessoa(r: dict, bens: dict) -> dict:
    sq = (r.get("SQ_CANDIDATO") or "").strip()
    return {
        "nome": (r.get("NM_CANDIDATO") or "").strip(),
        "urna": (r.get("NM_URNA_CANDIDATO") or "").strip(),
        "partido": (r.get("SG_PARTIDO") or "").strip(),
        "numero": (r.get("NR_CANDIDATO") or "").strip(),
        "genero": (r.get("DS_GENERO") or "").strip().title(),
        "situacao": (r.get("DS_SIT_TOT_TURNO") or "").strip().title(),
        "sq": sq,
        "bens": bens.get(sq),
    }


def eleitos(linhas: list[dict], bens: dict, tse_para_sim: dict[str, str]) -> dict[str, dict]:
    """{codigo_sim: {"prefeito":{}, "vice":{}, "vereadores":[...]}} só com eleições ordinárias."""
    por_ue: dict[str, dict] = {}
    chapas: dict[tuple, dict] = {}     # (ue, numero) -> linha do vice no último turno
    for r in linhas:
        tipo = sem_acento(r.get("NM_TIPO_ELEICAO") or r.get("DS_ELEICAO") or "")
        if "SUPLEMENTAR" in tipo:
            continue
        ue = (r.get("SG_UE") or "").strip()
        sim = tse_para_sim.get(ue)
        if not sim:
            continue
        cargo = (r.get("CD_CARGO") or "").strip()
        sit = sem_acento(r.get("DS_SIT_TOT_TURNO") or "").strip()
        turno = int((r.get("NR_TURNO") or "1").strip() or 1)
        m = por_ue.setdefault(sim, {"prefeito": None, "vice": None, "vereadores": []})
        if cargo == CARGO_VICE:
            k = (sim, (r.get("NR_CANDIDATO") or "").strip())
            if k not in chapas or turno >= chapas[k][0]:
                chapas[k] = (turno, r)
            continue
        if sit not in ELEITO:
            continue
        if cargo == CARGO_PREFEITO:
            m["prefeito"] = _pessoa(r, bens)
        elif cargo == CARGO_VEREADOR:
            if not any(v["sq"] == (r.get("SQ_CANDIDATO") or "").strip() for v in m["vereadores"]):
                m["vereadores"].append(_pessoa(r, bens))
    for sim, m in por_ue.items():
        if m["prefeito"]:
            v = chapas.get((sim, m["prefeito"]["numero"]))
            if v:
                m["vice"] = _pessoa(v[1], bens)
                m["vice"]["situacao"] = "Eleito"
        m["vereadores"].sort(key=lambda p: sem_acento(p["urna"] or p["nome"]))
    return por_ue
