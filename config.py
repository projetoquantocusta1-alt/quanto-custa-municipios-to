"""Projeto Quanto Custa — Prefeituras e câmaras de um estado pelo SICONFI (configuração).

Fonte das despesas: SICONFI (Tesouro Nacional), RREO Anexo 02. O mesmo código serve para qualquer estado: só o
bloco "ESTADO" abaixo muda de um repositório para outro (e o bloco CFG no começo de docs/uf.js).
"""
# --- ESTADO (muda em cada repositório) ---
UF = "TO"
CODIGO_UF_IBGE = 17
ESTADO = "Tocantins"
DO_ESTADO = "do Tocantins"
TOTAL_MUNICIPIOS = 139
TRIBUNAL = "TCE-TO"   # tribunal de contas que tem os dados nota a nota das prefeituras do estado
# --- fim do bloco ESTADO ---
ANO_INICIAL = 2017

USER_AGENT = "ProjetoQuantoCusta/1.0 (painel de transparencia com dados abertos)"
PAUSA_ENTRE_REQUISICOES = 0.15   # o SICONFI tem a sua própria pausa de 1 s (coletor/siconfi.py)

# --- TSE: candidatos e bens (eleições municipais) ---
ELEICOES_MUNICIPAIS = [2016, 2020, 2024]
MANDATO_DA_ELEICAO = {2016: (2017, 2020), 2020: (2021, 2024), 2024: (2025, 2028), 2028: (2029, 2032)}
TSE_CAND_ZIP = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"
TSE_BENS_ZIP = "https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_{ano}.zip"

# --- IBGE: população estimada (tabela 6579) e Censo 2022 (tabela 4714), municípios do estado (N3 = código da UF) ---
IBGE_ESTIMATIVA = ("https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/all/"
                   f"variaveis/9324?localidades=N6[N3[{CODIGO_UF_IBGE}]]")
IBGE_CENSO_2022 = ("https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022/"
                   f"variaveis/93?localidades=N6[N3[{CODIGO_UF_IBGE}]]")
SIDRA_ESTIMATIVA = f"https://apisidra.ibge.gov.br/values/t/6579/n6/in%20n3%20{CODIGO_UF_IBGE}/v/9324/p/all"
SIDRA_CENSO_2022 = f"https://apisidra.ibge.gov.br/values/t/4714/n6/in%20n3%20{CODIGO_UF_IBGE}/v/93/p/2022"

# --- IPCA (Banco Central, série 433) ---
IPCA_SGS = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"
            "?formato=json&dataInicial=01/01/{ano}")

# --- Teto do subsídio do vereador (Constituição, art. 29, VI) ---
# Percentual do subsídio do deputado estadual, conforme a população do município.
TETO_VEREADOR_FAIXAS = [(10_000, 0.20), (50_000, 0.30), (100_000, 0.40),
                        (300_000, 0.50), (500_000, 0.60), (float("inf"), 0.75)]
# Subsídio do deputado estadual = 75% do deputado federal (art. 27, §2º).
SUBSIDIO_DEP_FEDERAL = [((2015, 2), 33763.00), ((2023, 1), 39293.32), ((2023, 4), 41650.92),
                        ((2024, 2), 44008.52), ((2025, 2), 46366.19)]
