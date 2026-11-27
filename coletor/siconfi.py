"""SICONFI (Tesouro Nacional): despesa por função de cada município, de qualquer estado.

Usado para os estados cujo Tribunal de Contas ainda não é lido pelo robô (por exemplo, o TCM-BA não responde aos computadores do GitHub).
Fonte: RREO, Anexo 02 ("Demonstrativo da Execução das Despesas por Função/Subfunção"), que cada prefeitura
entrega a cada bimestre. O 6º bimestre é o ano inteiro.
  - total: "DESPESAS (EXCETO INTRA-ORÇAMENTÁRIAS)", igual ao gasto total do TCE-CE (conferido).
  - função 01 "Legislativa" = a câmara municipal. Conferido com o TCE-CE: em Fortaleza e Sobral (2025) a
    Legislativa do RREO, somando a parte intraorçamentária, é igual, centavo por centavo, ao empenhado da câmara.
  - colunas usadas: despesas empenhadas e liquidadas até o bimestre, nas duas partes do anexo
    (exceto intraorçamentárias + intraorçamentárias).
  - o RREO não traz o valor PAGO por função; traz o LIQUIDADO (serviço entregue e conferido, pronto para pagar).
API: https://apidatalake.tesouro.gov.br/ords/siconfi/tt/ (pedimos no máximo 1 consulta por segundo).
"""
import re
import time

from coletor import http

API = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
FUNCOES = ["Legislativa", "Judiciária", "Essencial à Justiça", "Administração", "Defesa Nacional", "Segurança Pública",
           "Relações Exteriores", "Assistência Social", "Previdência Social", "Saúde", "Trabalho", "Educação", "Cultura",
           "Direitos da Cidadania", "Urbanismo", "Habitação", "Saneamento", "Gestão Ambiental", "Ciência e Tecnologia",
           "Agricultura", "Organização Agrária", "Indústria", "Comércio e Serviços", "Comunicações", "Energia",
           "Transporte", "Desporto e Lazer", "Encargos Especiais"]
COL_EMP = "DESPESAS EMPENHADAS ATÉ O BIMESTRE"
COL_LIQ = "DESPESAS LIQUIDADAS ATÉ O BIMESTRE"
COL_RPNP = "INSCRITAS EM RESTOS A PAGAR NÃO PROCESSADOS"


_ultima = 0.0


def _get(caminho: str, params: dict) -> list[dict]:
    global _ultima
    itens, offset = [], 0
    while True:
        espera = 1.0 - (time.time() - _ultima)      # no máximo 1 consulta por segundo ao Tesouro
        if espera > 0:
            time.sleep(espera)
        _ultima = time.time()
        r = http.get(API + caminho, params={**params, "offset": offset}, timeout=(20, 120)).json()
        itens += r.get("items") or []
        if not r.get("hasMore"):
            return itens
        offset += r.get("limit") or 5000


def entes(uf: str) -> list[dict]:
    """Municípios do estado: [{"ibge", "nome", "populacao"}] (cadastro do SICONFI)."""
    out = [{"ibge": str(x["cod_ibge"]), "nome": x["ente"], "populacao": x.get("populacao")}
           for x in _get("entes", {}) if x.get("uf") == uf and x.get("esfera") == "M"]
    return sorted(out, key=lambda x: x["nome"])


def ler_rreo2(itens: list[dict]) -> dict | None:
    """Soma, por função, o empenhado e o liquidado até o bimestre (exceto intra + intra). None se vier vazio."""
    if not itens:
        return None
    fun: dict[str, list[float]] = {}
    total = [0.0, 0.0, 0.0]
    for x in itens:
        col, conta, v = x.get("coluna") or "", (x.get("conta") or "").strip(), float(x.get("valor") or 0)
        i = 0 if col.startswith(COL_EMP) else 1 if col.startswith(COL_LIQ) else 2 if col.startswith(COL_RPNP) else None
        if i is None:
            continue
        if conta in FUNCOES:
            fun.setdefault(conta, [0.0, 0.0, 0.0])[i] += v
        elif conta.startswith("DESPESAS (EXCETO INTRA"):
            # total da prefeitura sem a parte intraorçamentária (pagamentos entre órgãos do próprio município,
            # que contariam duas vezes). Igual ao gasto total do TCE-CE em Fortaleza e Sobral (2025).
            total[i] += v
    r = lambda a: [round(v, 2) for v in a]
    return {"periodo": itens[0].get("periodo"), "instituicao": itens[0].get("instituicao"),
            "populacao": itens[0].get("populacao"), "total": r(total), "funcoes": {k: r(v) for k, v in fun.items()}}


def rreo2(ibge: str, ano: int, periodo: int) -> dict | None:
    return ler_rreo2(_get("rreo", {"an_exercicio": ano, "nr_periodo": periodo, "co_tipo_demonstrativo": "RREO",
                                   "no_anexo": "RREO-Anexo 02", "id_ente": ibge}))


# ------------------------------------------------------------------ dívida (RGF, Anexo 02)
# Dívida Consolidada Líquida (DCL): o quanto a prefeitura deve a longo prazo, menos o que tem em caixa.
# Fonte: RGF, Anexo 02 ("Demonstrativo da Dívida Consolidada Líquida"), entregue a cada quadrimestre
# (ou semestre, nas cidades menores). O 3º quadrimestre (ou 2º semestre) é o retrato do fim do ano.
# A própria API já traz o % da dívida sobre a Receita Corrente Líquida e o limite legal (120% da RCL,
# Resolução 40/2001 do Senado), então não precisamos recalcular.
CONTAS_RGF2 = {
    "dc": "DividaConsolidada",                              # DÍVIDA CONSOLIDADA - DC (I)
    "contratual": "DividaContratual",                       # empréstimos, financiamentos, parcelamentos
    "precatorios": "PrecatoriosPosterioresA05052000VencidosENaoPagos",
    "parcelamentos": "RGF2ParcelamentoERenegociacaoDeDividas",
    "outras": "OutrasDividas",
    "deducoes": "DeducoesDaDividaConsolidada",              # DEDUÇÕES (II): caixa e aplicações
    "dcl": "DividaConsolidadaLiquida",                      # DCL (III) = (I - II)
    "rcl": "RGF2ReceitaCorrenteLiquida",                    # RECEITA CORRENTE LÍQUIDA - RCL (IV)
    "pct_dc": "PercentualDaDCSobreARCL",                    # % da DC sobre a RCL ajustada
    "pct_dcl": "PercentualDaDCLSobreARCL",                  # % da DCL sobre a RCL ajustada
    "limite": "LimiteDefinidoPorResolucaoDoSenadoFederal",  # 120% da RCL ajustada
    "limite_alerta": "LimiteDeAlerta",                      # 90% do limite (inciso III, §1º, art. 59 LRF)
}


def _periodo_num(col: str) -> int:
    """Nº do quadrimestre/semestre de uma coluna ('Até o 3º Quadrimestre' -> 3). -1 se não for período."""
    m = re.search(r"Até o (\d+)", col or "")
    return int(m.group(1)) if m else -1


def ler_rgf2(itens: list[dict]) -> dict | None:
    """Dívida consolidada do município no período mais recente entregue. None se vier vazio.
    Pega sempre a coluna do último quadrimestre/semestre presente (o retrato mais novo do ano)."""
    if not itens:
        return None
    pmax = max((_periodo_num(x.get("coluna")) for x in itens), default=-1)
    if pmax < 0:
        return None
    val = {x.get("cod_conta"): float(x.get("valor") or 0)
           for x in itens if _periodo_num(x.get("coluna")) == pmax}
    g = lambda k: round(val.get(CONTAS_RGF2[k], 0.0), 2)
    return {"periodo": pmax, "periodicidade": itens[0].get("periodicidade"),
            "populacao": itens[0].get("populacao"), "instituicao": itens[0].get("instituicao"),
            "dc": g("dc"), "contratual": g("contratual"), "precatorios": g("precatorios"),
            "parcelamentos": g("parcelamentos"), "outras": g("outras"), "deducoes": g("deducoes"),
            "dcl": g("dcl"), "rcl": g("rcl"), "pct_dc": g("pct_dc"), "pct_dcl": g("pct_dcl"),
            "limite": g("limite"), "limite_alerta": g("limite_alerta")}


def rgf2(ibge: str, ano: int, ate_periodo: int = 3) -> dict | None:
    """RGF Anexo 02 (dívida) de um município/ano. Procura o retrato mais novo disponível:
    do quadrimestre 'ate_periodo' para trás; se a cidade entrega semestral, cai para o semestre.
    Para o primeiro período não entregue, devolve None (a cidade ainda não prestou contas)."""
    base = {"an_exercicio": ano, "co_tipo_demonstrativo": "RGF", "no_anexo": "RGF-Anexo 02",
            "co_esfera": "M", "co_poder": "E", "id_ente": ibge}
    for per in range(ate_periodo, 0, -1):
        d = ler_rgf2(_get("rgf", {**base, "in_periodicidade": "Q", "nr_periodo": per}))
        if d:
            return d
    for per in (2, 1):
        d = ler_rgf2(_get("rgf", {**base, "in_periodicidade": "S", "nr_periodo": per}))
        if d:
            return d
    return None
