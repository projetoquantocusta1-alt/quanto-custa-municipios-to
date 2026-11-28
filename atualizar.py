"""Robô das prefeituras e câmaras de um estado (SICONFI); o estado está em config.py.

Uso:
    python atualizar.py                    # SICONFI (o que falta) e monta o site
    python atualizar.py --semanal          # também TSE (eleitos), IBGE (população) e IPCA
    python atualizar.py --so-montar        # só remonta o site com o que já está salvo
    python atualizar.py --minutos 90       # tempo máximo de consultas ao SICONFI

Brutos (dados_brutos/):
    siconfi/entes.json, siconfi/<ibge>.json   despesa por função de cada ano (RREO, Anexo 02)
    tse/eleitos_AAAA.json                     eleitos por município (chave: código IBGE)
    populacao.json, ipca.json
Site (docs/dados/):
    meta.json, resumo.json (uma linha por município e ano), m/<ibge>.json (detalhe do município)
"""
import argparse
import difflib
import json
import logging
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import config
from coletor import eleitos as EL
from coletor import http, ipca, populacao, siconfi
from coletor.texto import chave_nome

RAIZ = Path(__file__).parent
BRUTOS = RAIZ / "dados_brutos"
SAIDA = RAIZ / "docs" / "dados"
log = logging.getLogger(config.UF.lower())


def ler(p: Path, padrao=None):
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else padrao
    except json.JSONDecodeError:
        return padrao


def gravar(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")


def r2(x):
    return None if x is None else round(x, 2)


# ------------------------------------------------------------------ SICONFI
def ultimo_bimestre_possivel(ano: int, hoje: date) -> int:
    """Último bimestre que já pode ter sido entregue (prazo: 30 dias depois do fim do bimestre)."""
    if ano < hoje.year:
        return 6
    meses_completos = hoje.month - 1 - (1 if hoje.day < 30 else 0)
    return max(0, min(6, meses_completos // 2))


def entes(hoje: date) -> list[dict]:
    arq = BRUTOS / "siconfi" / "entes.json"
    lista = ler(arq)
    if not lista or lista[0].get("_baixado") != hoje.isoformat()[:7]:
        try:
            novos = siconfi.entes(config.UF)
            if len(novos) >= 0.95 * config.TOTAL_MUNICIPIOS:
                novos[0]["_baixado"] = hoje.isoformat()[:7]
                gravar(arq, novos)
                lista = novos
        except Exception as e:  # noqa: BLE001
            log.warning("lista de municípios do SICONFI indisponível (%s); usa a anterior", e)
    return lista or []


def coletar_siconfi(hoje: date, limite_s: float) -> int:
    """RREO Anexo 02 de cada município e ano, do ano mais novo para o mais antigo.
    Ano com o 6º bimestre guardado não é consultado de novo; ano aberto procura bimestres mais novos;
    prefeitura que não entregou fica anotada ('falta') e é consultada de novo depois de 15 dias."""
    pasta = BRUTOS / "siconfi"
    lista = entes(hoje)
    t0, feitos = time.time(), 0
    for ano in range(hoje.year, config.ANO_INICIAL - 1, -1):
        maxp = ultimo_bimestre_possivel(ano, hoje)
        if not maxp:
            continue
        for e in lista:
            if time.time() - t0 > limite_s:
                log.warning("tempo esgotado; o resto fica para a próxima execução (%d consultas)", feitos)
                return feitos
            arq = pasta / f"{e['ibge']}.json"
            d = ler(arq, {}) or {}
            atual = d.get(str(ano)) or {}
            if (atual.get("periodo") or 0) >= maxp:
                continue
            if atual.get("falta") and hoje.toordinal() - date.fromisoformat(atual["falta"]).toordinal() < 15:
                continue
            achado = None
            for p in range(maxp, (atual.get("periodo") or 0), -1):
                try:
                    achado = siconfi.rreo2(e["ibge"], ano, p)
                except http.SiteForaDoAr as x:
                    log.error("%s", x)
                    return feitos
                except Exception as x:  # noqa: BLE001
                    log.warning("%s %s %d/%d: %s", e["nome"], e["ibge"], ano, p, x)
                feitos += 1
                if achado or ano < hoje.year - 1:   # ano antigo: só o 6º bimestre (o ano inteiro) interessa
                    break
            if achado:
                achado["baixado_em"] = hoje.isoformat()
                d[str(ano)] = achado
            elif not atual.get("periodo"):
                d[str(ano)] = {"falta": hoje.isoformat()}
            gravar(arq, d)
        log.info("SICONFI %d: pronto", ano)
    return feitos


def ultimo_quadri_possivel(ano: int, hoje: date) -> int:
    """Último quadrimestre do RGF que já pode ter sido entregue (prazo: 30 dias após o fim do quadrimestre).
    Quadrimestres terminam em abr (1), ago (2) e dez (3)."""
    if ano < hoje.year:
        return 3
    if hoje.month >= 10:       # 3º quadrimestre do ano anterior já fechou; o 2º deste ano sai ~out
        return 2
    if hoje.month >= 6:        # 1º quadrimestre (fim abr) entregue ~jun
        return 1
    return 0


def coletar_rgf(hoje: date, limite_s: float) -> int:
    """Dívida consolidada (RGF, Anexo 02) de cada município e ano, do mais novo para o mais antigo.
    Mesmo esquema do RREO: ano fechado é guardado e não se repete; ano aberto procura o quadrimestre
    mais novo; quem não entregou fica anotado ('falta') e é tentado de novo depois de 15 dias."""
    pasta = BRUTOS / "rgf"
    lista = ler(BRUTOS / "siconfi" / "entes.json", []) or []
    t0, feitos = time.time(), 0
    for ano in range(hoje.year, config.ANO_INICIAL - 1, -1):
        maxp = ultimo_quadri_possivel(ano, hoje)
        if not maxp:
            continue
        for e in lista:
            if time.time() - t0 > limite_s:
                log.warning("tempo da dívida esgotado; o resto fica para a próxima execução (%d consultas)", feitos)
                return feitos
            arq = pasta / f"{e['ibge']}.json"
            d = ler(arq, {}) or {}
            atual = d.get(str(ano)) or {}
            fechado = (atual.get("periodicidade") == "Q" and (atual.get("periodo") or 0) >= 3) or \
                      (atual.get("periodicidade") == "S" and (atual.get("periodo") or 0) >= 2)
            if fechado or (ano < hoje.year and (atual.get("periodo") or 0) >= maxp):
                continue
            if ano == hoje.year and (atual.get("periodo") or 0) >= maxp and atual.get("periodicidade") == "Q":
                continue
            if atual.get("falta") and hoje.toordinal() - date.fromisoformat(atual["falta"]).toordinal() < 15:
                continue
            achado = None
            try:
                achado = siconfi.rgf2(e["ibge"], ano, maxp)
            except http.SiteForaDoAr as x:
                log.error("%s", x)
                return feitos
            except Exception as x:  # noqa: BLE001
                log.warning("RGF %s %s %d: %s", e["nome"], e["ibge"], ano, x)
            feitos += 1
            if achado:
                achado["baixado_em"] = hoje.isoformat()
                d[str(ano)] = achado
            elif not atual.get("periodo"):
                d[str(ano)] = {"falta": hoje.isoformat()}
            gravar(arq, d)
        log.info("RGF (dívida) %d: pronto", ano)
    return feitos


# ------------------------------------------------------------------ TSE, IBGE, IPCA
def tse(lista: list[dict], refazer=False) -> int:
    """Eleitos de cada eleição municipal. O TSE usa códigos próprios (SG_UE); a ligação com o IBGE é pelo nome."""
    por_nome = {chave_nome(e["nome"]): e["ibge"] for e in lista}
    ok = 0
    for ano in config.ELEICOES_MUNICIPAIS:
        p = BRUTOS / "tse" / f"eleitos_{ano}.json"
        if p.exists() and not refazer:
            ok += 1
            continue
        try:
            cand = EL._csv_do_zip(http.get(config.TSE_CAND_ZIP.format(ano=ano), timeout=600).content, config.UF)
            try:
                bens = EL.bens_por_candidato(http.get(config.TSE_BENS_ZIP.format(ano=ano), timeout=600).content, config.UF)
            except Exception as e:  # noqa: BLE001
                log.warning("TSE %s: bens indisponíveis (%s)", ano, e)
                bens = {}
            tse_para_ibge, sem = {}, set()
            for r in cand:
                ue, nome = (r.get("SG_UE") or "").strip(), r.get("NM_UE") or ""
                if not ue or ue in tse_para_ibge:
                    continue
                k = chave_nome(nome)
                i = por_nome.get(k) or por_nome.get((difflib.get_close_matches(k, list(por_nome), 1, 0.9) or [""])[0])
                if i:
                    tse_para_ibge[ue] = i
                else:
                    sem.add(nome)
            res = EL.eleitos(cand, bens, tse_para_ibge)
            log.info("TSE %s: %d municípios, %d vereadores; sem ligação com o IBGE: %s",
                     ano, len(res), sum(len(v["vereadores"]) for v in res.values()), sorted(sem)[:10])
            gravar(p, {"municipios": res, "sem_ligacao": sorted(sem)})
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.error("TSE %s falhou: %s", ano, e)
    return ok


def ibge():
    try:
        pop = populacao.baixar_populacao()
        doUF = {k: v for k, v in pop.items() if k.startswith(str(config.CODIGO_UF_IBGE))}
        if len(doUF) >= 0.95 * config.TOTAL_MUNICIPIOS:
            gravar(BRUTOS / "populacao.json", doUF)
            log.info("IBGE: população de %d municípios", len(doUF))
    except Exception as e:  # noqa: BLE001
        log.warning("IBGE indisponível (%s); mantém a anterior", e)


def atualizar_ipca():
    try:
        gravar(BRUTOS / "ipca.json", ipca.fatores_por_ano(ipca.baixar_ipca(config.ANO_INICIAL)))
    except Exception as e:  # noqa: BLE001
        log.warning("IPCA indisponível (%s); mantém o anterior", e)


# ------------------------------------------------------------------ montagem
def subsidio_dep_federal(ano: int, mes: int) -> float:
    v = config.SUBSIDIO_DEP_FEDERAL[0][1]
    for (a, m), x in config.SUBSIDIO_DEP_FEDERAL:
        if (ano, mes) >= (a, m):
            v = x
    return v


def teto_vereador_mensal(ano: int, pop: int | None) -> float | None:
    """Média mensal, no ano, do teto constitucional do subsídio do vereador."""
    if not pop:
        return None
    pct = next(p for lim, p in config.TETO_VEREADOR_FAIXAS if pop <= lim)
    return round(sum(subsidio_dep_federal(ano, m) for m in range(1, 13)) / 12 * 0.75 * pct, 2)


def eleicao_do_ano(ano: int) -> int | None:
    for el, (ini, fim) in config.MANDATO_DA_ELEICAO.items():
        if ini <= ano <= fim:
            return el
    return None


CAMPOS = ["periodo", "populacao", "gasto_total", "camara", "camara_liquidado", "n_vereadores", "teto_subsidio_vereador", "alerta"]

# Valor da câmara que não dá para aceitar como está (fica fora dos totais e dos rankings, com o aviso):
#  - "zerada": a função Legislativa veio zerada (ou negativa) no relatório da prefeitura; a despesa da câmara
#    provavelmente foi lançada em outra função ou não foi consolidada;
#  - "fora_do_padrao": no ano fechado, acima de 8% do gasto da prefeitura (a Constituição limita a câmara a 7%,
#    no máximo; no ano em andamento a conta não vale, porque a câmara empenha o ano todo no começo), ou mais
#    de 4 vezes (ou, no ano fechado, menos de 0,3 vez) a mediana da própria câmara nos outros anos; provável erro de
#    classificação no relatório. Aumento de um ano para o outro, sozinho, não é marcado (pode ser real).
FATOR_FORA = 4.0
LIMITE_PCT_PREFEITURA = 0.08


def alertas_camara(d: dict, desde: int) -> dict:
    validos = {a: x["funcoes"].get("Legislativa", [0])[0] for a, x in d.items()
               if not x.get("falta") and int(a) >= desde}
    out = {}
    for a, v in validos.items():
        outros = sorted(w for b, w in validos.items() if b != a and w > 0)
        med = outros[len(outros) // 2] if len(outros) >= 3 else None
        x = d[a]
        if v <= 0:
            out[a] = {"tipo": "zerada", "mediana": med}
        elif (x.get("periodo") == 6 and x["total"][0] > 0 and v / x["total"][0] > LIMITE_PCT_PREFEITURA) or (med and (v > FATOR_FORA * med or (x.get("periodo") == 6 and v < 0.3 * med))):
            out[a] = {"tipo": "fora_do_padrao", "mediana": med}
    return out


def prever_dcl(serie: list[tuple[int, float]], ano_alvo: int) -> dict | None:
    """Projeção simples (tendência linear) da dívida líquida para 'ano_alvo' (o ano seguinte ao
    último com dado). Fita a reta nos anos fechados; precisa de pelo menos 3. Sempre uma estimativa.
    A DCL pode ficar negativa (cidade com mais caixa que dívida), então não é cortada em zero."""
    if len(serie) < 3:
        return None
    xs = [a for a, _ in serie]
    ys = [v for _, v in serie]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return None
    b = sxy / sxx
    pred = (my - b * mx) + b * ano_alvo
    return {"ano": ano_alvo, "dcl": round(pred, 2), "metodo": "tendência dos últimos anos"}


def divida_do_municipio(ibge: str) -> dict | None:
    """Lê o bruto do RGF de um município e monta o bloco de dívida (séries por ano + previsão)."""
    rgf = ler(BRUTOS / "rgf" / f"{ibge}.json", {}) or {}
    anos = {}
    for ano_s, x in sorted(rgf.items()):
        if x.get("falta") or int(ano_s) < config.ANO_INICIAL:
            continue
        fechado = (x.get("periodicidade") == "Q" and (x.get("periodo") or 0) >= 3) or \
                  (x.get("periodicidade") == "S" and (x.get("periodo") or 0) >= 2)
        anos[ano_s] = {"periodo": x.get("periodo"), "periodicidade": x.get("periodicidade"), "fechado": fechado,
                       "populacao": x.get("populacao"),
                       "dc": x.get("dc"), "contratual": x.get("contratual"), "precatorios": x.get("precatorios"),
                       "parcelamentos": x.get("parcelamentos"), "outras": x.get("outras"), "deducoes": x.get("deducoes"),
                       "dcl": x.get("dcl"), "rcl": x.get("rcl"), "pct_dc": x.get("pct_dc"), "pct_dcl": x.get("pct_dcl"),
                       "limite": x.get("limite"), "limite_alerta": x.get("limite_alerta")}
    if not anos:
        return None
    serie = sorted((int(a), v["dcl"]) for a, v in anos.items() if v["fechado"] and v["dcl"] is not None)
    ultimo = max(anos)
    return {"anos": anos, "ultimo": ultimo, "previsao": prever_dcl(serie, int(ultimo) + 1)}


def montar(hoje: date):
    lista = ler(BRUTOS / "siconfi" / "entes.json", []) or []
    pop = ler(BRUTOS / "populacao.json", {}) or {}
    ip = ler(BRUTOS / "ipca.json", {"fatores": {}, "referencia": None})
    eleitos = {el: (ler(BRUTOS / "tse" / f"eleitos_{el}.json", {}) or {}).get("municipios", {}) for el in config.ELEICOES_MUNICIPAIS}
    resumo, cobertura, faltas, parciais, periodos, lista_alertas = [], Counter(), {}, {}, {}, {}
    anos = set()
    divida_resumo, div_anos_cobertos = [], set()
    for e in lista:
        i = e["ibge"]
        d = ler(BRUTOS / "siconfi" / f"{i}.json", {}) or {}
        det = {"ibge": i, "nome": e["nome"], "anos": {}, "eleitos": {}}
        for el, res in eleitos.items():
            x = res.get(i)
            if x:
                det["eleitos"][str(el)] = x
        linhas = {}
        alertas = alertas_camara(d, config.ANO_INICIAL)
        for ano_s, x in sorted(d.items()):
            ano = int(ano_s)
            if ano < config.ANO_INICIAL:
                continue
            if x.get("falta"):
                faltas.setdefault(ano_s, []).append(e["nome"])
                continue
            p = populacao.populacao_no_ano(pop.get(i) or {}, ano) or x.get("populacao")
            el = eleicao_do_ano(ano)
            n_ver = len(((eleitos.get(el) or {}).get(i) or {}).get("vereadores") or []) or None
            cam = (x.get("funcoes") or {}).get("Legislativa") or [0.0, 0.0, 0.0]
            teto = teto_vereador_mensal(ano, p)
            fechado = x["periodo"] == 6
            if not fechado and ano < hoje.year:
                parciais.setdefault(ano_s, []).append([e["nome"], x["periodo"]])
            det["anos"][ano_s] = {"periodo": x["periodo"], "fechado": fechado, "populacao": p, "n_vereadores": n_ver,
                                  "gasto_total": x["total"][0], "gasto_total_liquidado": x["total"][1],
                                  "camara": cam[0], "camara_liquidado": cam[1], "camara_rp_nao_processados": cam[2],
                                  "funcoes": {k: v[:2] for k, v in sorted(x["funcoes"].items(), key=lambda kv: -kv[1][0])},
                                  "teto_subsidio_vereador": teto, "alerta": alertas.get(ano_s)}
            linhas[ano_s] = [x["periodo"], p, x["total"][0], cam[0], cam[1], n_ver, teto, (alertas.get(ano_s) or {}).get("tipo")]
            if ano_s in alertas:
                lista_alertas.setdefault(ano_s, []).append([e["nome"], alertas[ano_s]["tipo"], cam[0], alertas[ano_s]["mediana"]])
            cobertura[ano_s] += 1
            periodos.setdefault(ano_s, Counter())[x["periodo"]] += 1
            anos.add(ano)
        div = divida_do_municipio(i)
        if div:
            det["divida"] = div
            # ranking por ano: cada ano com dado vira [dcl, % da receita, população]; acima/alerta saem do %
            # (acima = % > 120, o teto legal; alerta = % > 108), igual ao limite da lei.
            por_ano = {a: [v["dcl"], v.get("pct_dcl"), v.get("populacao"), 1 if v["fechado"] else 0]
                       for a, v in div["anos"].items() if v.get("dcl") is not None}
            if por_ano:
                ult = div["ultimo"]
                pu = por_ano.get(ult) or next(iter(por_ano.values()))
                pct = pu[1] or 0
                divida_resumo.append({"ibge": i, "nome": e["nome"], "ano": ult, "fechado": div["anos"][ult]["fechado"],
                                      "dcl": pu[0], "pct_dcl": pu[1], "populacao": pu[2],
                                      "acima": pct > 120, "alerta": 108 < pct <= 120, "por_ano": por_ano})
            for a in div["anos"]:
                div_anos_cobertos.add(int(a))
        gravar(SAIDA / "m" / f"{i}.json", det)
        resumo.append({"ibge": i, "nome": e["nome"], "anos": linhas})
    gravar(SAIDA / "resumo.json", {"campos": CAMPOS, "municipios": resumo})
    divida_resumo.sort(key=lambda r: -(r["dcl"] or 0))
    gravar(SAIDA / "divida.json", {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "uf": config.UF, "estado": config.ESTADO, "do_estado": config.DO_ESTADO,
        "anos": sorted(div_anos_cobertos), "com_divida": len(divida_resumo),
        "acima_do_limite": sorted(r["nome"] for r in divida_resumo if r["acima"]),
        "em_alerta": sorted(r["nome"] for r in divida_resumo if r["alerta"] and not r["acima"]),
        "municipios": divida_resumo,
        "fonte": "SICONFI (Tesouro Nacional), RGF Anexo 02 (Dívida Consolidada Líquida)",
    })
    sem_tse = sorted({n for el in config.ELEICOES_MUNICIPAIS for n in (ler(BRUTOS / "tse" / f"eleitos_{el}.json", {}) or {}).get("sem_ligacao", [])})
    gravar(SAIDA / "meta.json", {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "uf": config.UF, "estado": config.ESTADO, "do_estado": config.DO_ESTADO, "tribunal": config.TRIBUNAL,
        "total_municipios": len(lista), "anos": sorted(anos), "ipca": ip,
        "cobertura": dict(cobertura), "faltas": {a: sorted(v) for a, v in faltas.items()},
        "parciais": parciais, "alertas_camara": lista_alertas, "periodo_mais_comum": {a: c.most_common(1)[0][0] for a, c in periodos.items()},
        "tse_sem_ligacao": sem_tse, "eleicoes": config.ELEICOES_MUNICIPAIS,
        "fonte": "SICONFI (Tesouro Nacional), RREO Anexo 02",
    })
    log.info("site montado: %d municípios; cobertura %s", len(lista), dict(sorted(cobertura.items())))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--so-montar", action="store_true")
    ap.add_argument("--semanal", action="store_true")
    ap.add_argument("--minutos", type=float, default=90)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    hoje = date.today()
    if not a.so_montar:
        lista = entes(hoje)
        if a.semanal or not (BRUTOS / "ipca.json").exists():
            atualizar_ipca()
            ibge()
            tse(lista)
        t0 = time.time()
        coletar_siconfi(hoje, a.minutos * 60 * 0.6)
        coletar_rgf(hoje, max(0.0, a.minutos * 60 - (time.time() - t0)))
    montar(hoje)
    return 0


if __name__ == "__main__":
    sys.exit(main())
