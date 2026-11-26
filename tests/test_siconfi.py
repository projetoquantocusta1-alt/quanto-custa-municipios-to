import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coletor import siconfi  # noqa: E402


def _i(rot, conta, col, v, p=6):
    return {"rotulo": rot, "conta": conta, "coluna": col, "valor": v, "periodo": p, "instituicao": "Prefeitura X"}


def test_legislativa_soma_intra_e_total_sem_intra():
    E, I = "Total das Despesas Exceto Intra-Orçamentárias", "Total das Despesas Intra-Orçamentárias"
    itens = [
        _i(E, "DESPESAS (EXCETO INTRA-ORÇAMENTÁRIAS) (I)", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)", 1000),
        _i(E, "Legislativa", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)", 90),
        _i(E, "Ação Legislativa", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)", 90),
        _i(E, "Legislativa", "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (d)", 80),
        _i(E, "Legislativa", "DESPESAS EMPENHADAS NO BIMESTRE", 5),
        _i(I, "DESPESAS (INTRA-ORÇAMENTÁRIAS) (II)", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)", 50),
        _i(I, "Legislativa", "DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)", 10),
        _i(I, "Legislativa", "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (d)", 10),
    ]
    r = siconfi.ler_rreo2(itens)
    assert r["funcoes"]["Legislativa"][:2] == [100, 90]
    assert r["total"][0] == 1000 and "Ação Legislativa" not in r["funcoes"]


def test_vazio():
    assert siconfi.ler_rreo2([]) is None
