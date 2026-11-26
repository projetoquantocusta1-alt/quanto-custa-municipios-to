"""População dos municípios (IBGE)."""
import config
from coletor import http


# ------------------------------------------------------------------ população
def ler_ibge(json_ibge) -> dict[str, dict[int, int]]:
    """{ibge7: {ano: pop}} a partir da resposta da API de agregados do IBGE."""
    out: dict[str, dict[int, int]] = {}
    for var in json_ibge or []:
        for res in var.get("resultados", []):
            for s in res.get("series", []):
                cod = str(s["localidade"]["id"])
                for ano, v in (s.get("serie") or {}).items():
                    try:
                        out.setdefault(cod, {})[int(ano)] = int(v)
                    except (TypeError, ValueError):
                        pass
    return out


def ler_sidra(linhas) -> dict[str, dict[int, int]]:
    """{ibge7: {ano: pop}} a partir da API do SIDRA (apisidra.ibge.gov.br/values/...).
    A 1ª linha é o cabeçalho; nas outras, o município e o ano vêm em campos D?C (a ordem varia)."""
    out: dict[str, dict[int, int]] = {}
    for r in (linhas or [])[1:]:
        if not isinstance(r, dict):
            continue
        cods = [str(v) for k, v in r.items() if k.startswith("D") and k.endswith("C")]
        mun = next((c for c in cods if len(c) == 7 and c.isdigit()), None)
        ano = next((c for c in cods if len(c) == 4 and c.isdigit() and 1990 <= int(c) <= 2100), None)
        try:
            v = int(float(str(r.get("V", "")).replace(",", ".")))
        except ValueError:
            continue
        if mun and ano:
            out.setdefault(mun, {})[int(ano)] = v
    return out


def _uma_fonte(api, sidra):
    """Tenta a API de agregados; se não responder, o SIDRA (outro servidor do IBGE)."""
    try:
        r = ler_ibge(http.get(api, timeout=(20, 120)).json())
        if r:
            return r
    except Exception:  # noqa: BLE001
        pass
    return ler_sidra(http.get(sidra, timeout=(20, 120)).json())


def baixar_populacao() -> dict[str, dict[int, int]]:
    pop = _uma_fonte(config.IBGE_ESTIMATIVA, config.SIDRA_ESTIMATIVA)
    try:
        censo = _uma_fonte(config.IBGE_CENSO_2022, config.SIDRA_CENSO_2022)
        for cod, s in censo.items():
            pop.setdefault(cod, {}).update(s)
    except Exception:  # noqa: BLE001 — o censo é complemento; sem ele vale a estimativa mais próxima
        pass
    return pop


def populacao_no_ano(serie: dict, ano: int) -> int | None:
    """Ano exato; senão, o ano disponível mais próximo (o anterior em caso de empate)."""
    if not serie:
        return None
    s = {int(k): v for k, v in serie.items()}
    if ano in s:
        return s[ano]
    melhor = min(s, key=lambda a: (abs(a - ano), a > ano))
    return s[melhor]
