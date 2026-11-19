"""
Etapa 2 - Conciliação de caixa.

Cruza o que o PDV diz que foi vendido com o que realmente entrou:

- Cartão  -> cada venda precisa ter uma transação na maquininha com o mesmo valor
- PIX     -> cada venda precisa ter um PIX recebido no extrato do banco
- Dinheiro -> a soma das vendas em dinheiro do turno precisa bater com a gaveta

Saída em resultados/:
- pendencias.csv          -> cada venda que não foi confirmada (cartão ou PIX)
- conciliacao_gaveta.csv  -> esperado x contado de cada turno de cada operador
- resumo_operador.csv     -> diferença total por operador e forma de pagamento

Uso:  python src/conciliacao.py
(rode antes o src/limpeza.py)
"""

from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
TRATADOS = PASTA / "dados" / "tratados"
RESULTADOS = PASTA / "resultados"

TOLERANCIA_GAVETA = 1.00  # diferença de até R$ 1 na gaveta é considerada troco


def carregar():
    vendas = pd.read_csv(TRATADOS / "vendas.csv", parse_dates=["data_hora"])
    maquininha = pd.read_csv(TRATADOS / "maquininha.csv")
    pix = pd.read_csv(TRATADOS / "pix.csv")
    fechamento = pd.read_csv(TRATADOS / "fechamento.csv")
    return vendas, maquininha, pix, fechamento


def conciliar_cartao(vendas: pd.DataFrame, maquininha: pd.DataFrame) -> pd.DataFrame:
    """Vendas no cartão sem transação correspondente (ou com valor diferente)."""
    cartao = vendas[vendas["forma_pagamento"].isin(["Crédito", "Débito"])]
    cruzado = cartao.merge(
        maquininha[["id_venda_pdv", "valor_bruto"]],
        left_on="id_venda", right_on="id_venda_pdv", how="left",
    )
    nao_encontradas = cruzado["valor_bruto"].isna()
    valor_diferente = ~nao_encontradas & (cruzado["valor_bruto"].round(2) != cruzado["valor"].round(2))

    cruzado["motivo"] = None
    cruzado.loc[nao_encontradas, "motivo"] = "Não consta na maquininha"
    cruzado.loc[valor_diferente, "motivo"] = "Valor diferente na maquininha"
    cruzado["valor_recebido"] = cruzado["valor_bruto"].fillna(0)
    return cruzado[cruzado["motivo"].notna()]


def conciliar_pix(vendas: pd.DataFrame, pix: pd.DataFrame) -> pd.DataFrame:
    """Vendas em PIX que não aparecem no extrato do banco."""
    vendas_pix = vendas[vendas["forma_pagamento"] == "PIX"]
    cruzado = vendas_pix.merge(
        pix[["id_venda_pdv", "valor"]].rename(columns={"valor": "valor_pix"}),
        left_on="id_venda", right_on="id_venda_pdv", how="left",
    )
    cruzado["motivo"] = None
    cruzado.loc[cruzado["valor_pix"].isna(), "motivo"] = "PIX não recebido no banco"
    cruzado["valor_recebido"] = cruzado["valor_pix"].fillna(0)
    return cruzado[cruzado["motivo"].notna()]


def conciliar_gaveta(vendas: pd.DataFrame, fechamento: pd.DataFrame) -> pd.DataFrame:
    """Compara o dinheiro esperado (vendas em dinheiro) com o contado na gaveta."""
    vendas["data"] = vendas["data_hora"].dt.date.astype(str)
    esperado = (
        vendas[vendas["forma_pagamento"] == "Dinheiro"]
        .groupby(["data", "turno", "operador"], as_index=False)["valor"].sum()
        .rename(columns={"valor": "dinheiro_esperado"})
    )
    gaveta = fechamento.merge(esperado, on=["data", "turno", "operador"], how="left")
    gaveta["dinheiro_esperado"] = gaveta["dinheiro_esperado"].fillna(0).round(2)
    gaveta["diferenca"] = (gaveta["dinheiro_em_gaveta"] - gaveta["dinheiro_esperado"]).round(2)

    def status(d):
        if abs(d) <= TOLERANCIA_GAVETA:
            return "OK"
        return "Falta" if d < 0 else "Sobra"

    gaveta["status"] = gaveta["diferenca"].apply(status)
    return gaveta[["data", "turno", "operador", "dinheiro_esperado",
                   "dinheiro_em_gaveta", "diferenca", "status"]]


def main():
    RESULTADOS.mkdir(exist_ok=True)
    vendas, maquininha, pix, fechamento = carregar()

    # 1. Pendências de cartão e PIX (venda registrada, dinheiro não entrou)
    pendencias = pd.concat([conciliar_cartao(vendas, maquininha), conciliar_pix(vendas, pix)])
    pendencias["diferenca"] = (pendencias["valor_recebido"] - pendencias["valor"]).round(2)
    pendencias = pendencias[["id_venda", "data_hora", "turno", "operador", "forma_pagamento",
                             "valor", "valor_recebido", "diferenca", "motivo"]]
    pendencias.sort_values("data_hora").to_csv(RESULTADOS / "pendencias.csv", index=False)

    # 2. Gaveta de dinheiro
    gaveta = conciliar_gaveta(vendas, fechamento)
    gaveta.to_csv(RESULTADOS / "conciliacao_gaveta.csv", index=False)

    # 3. Resumo por operador e forma de pagamento
    dif_gaveta = (gaveta.groupby("operador")["diferenca"]
                  .apply(lambda s: s[s.abs() > TOLERANCIA_GAVETA].sum())
                  .rename("Dinheiro"))
    dif_outros = pendencias.pivot_table(index="operador", columns="forma_pagamento",
                                        values="diferenca", aggfunc="sum", fill_value=0)
    resumo = dif_outros.join(dif_gaveta, how="outer").fillna(0).round(2)
    resumo["Total"] = resumo.sum(axis=1).round(2)
    resumo = resumo.sort_values("Total")
    resumo.to_csv(RESULTADOS / "resumo_operador.csv")

    # 4. Painel no terminal
    total_vendido = vendas["valor"].sum()
    perda_total = resumo["Total"].sum()
    faltas = gaveta[gaveta["status"] == "Falta"]

    print("CONCILIAÇÃO DE CAIXA - OUTUBRO/2026")
    print("=" * 40)
    print(f"Total vendido no PDV ............ R$ {total_vendido:>12,.2f}")
    print(f"Diferença total encontrada ...... R$ {perda_total:>12,.2f}  "
          f"({perda_total / total_vendido:.2%} do faturamento)")
    print()
    print("Onde está a diferença:")
    for motivo, grupo in pendencias.groupby("motivo"):
        print(f"  - {motivo}: {len(grupo)} vendas, R$ {grupo['diferenca'].sum():,.2f}")
    print(f"  - Faltas na gaveta de dinheiro: {len(faltas)} turnos, R$ {faltas['diferenca'].sum():,.2f}")
    print()
    print("Diferença por operador (R$):")
    print(resumo.to_string())

    pior = resumo.index[0]
    faltas_pior = faltas[faltas["operador"] == pior]
    print()
    print(f">> Ponto de atenção: {pior} concentra {resumo.loc[pior, 'Total'] / perda_total:.0%} "
          f"da diferença, com falta na gaveta em {len(faltas_pior)} dos "
          f"{(gaveta['operador'] == pior).sum()} turnos trabalhados.")
    print(f"\nArquivos salvos em: {RESULTADOS}")


if __name__ == "__main__":
    main()
