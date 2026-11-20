"""
Etapa 3 - Carrega os dados no banco SQLite usando o modelo estrela.

Lê os arquivos limpos (dados/tratados/) e os resultados da conciliação
(resultados/) e monta o banco banco/caixa.db com:

- dim_data, dim_operador, dim_forma_pagamento  -> tabelas dimensão
- fato_vendas, fato_gaveta                     -> tabelas fato

As tabelas são criadas pelo arquivo sql/01_modelo_estrela.sql. Este script
só prepara os dados com pandas e insere nas tabelas.

Uso:  python src/carregar_banco.py
(rode antes o src/limpeza.py e o src/conciliacao.py)
"""

import sqlite3
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
TRATADOS = PASTA / "dados" / "tratados"
RESULTADOS = PASTA / "resultados"
BANCO = PASTA / "banco" / "caixa.db"
SQL_MODELO = PASTA / "sql" / "01_modelo_estrela.sql"

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# Como cada forma de pagamento é conferida (ver src/conciliacao.py)
FORMAS = [
    ("Crédito", "Cartão", "Extrato da maquininha"),
    ("Débito", "Cartão", "Extrato da maquininha"),
    ("PIX", "PIX", "Extrato do banco"),
    ("Dinheiro", "Dinheiro", "Contagem da gaveta"),
]

# Nome curto do status para o motivo que vem do pendencias.csv
STATUS_PENDENCIA = {
    "Não consta na maquininha": "Não consta na maquininha",
    "Valor diferente na maquininha": "Valor diferente na maquininha",
    "PIX não recebido no banco": "PIX não recebido",
}


def id_data(datas: pd.Series) -> pd.Series:
    """Transforma '2026-10-31' na chave 20261031."""
    return pd.to_datetime(datas).dt.strftime("%Y%m%d").astype(int)


def montar_dim_data(vendas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha para cada dia do período das vendas (sem pular nenhum dia)."""
    dias = pd.date_range(vendas["data"].min(), vendas["data"].max(), freq="D")
    dim = pd.DataFrame({"data_dt": dias})
    dim["id_data"] = dim["data_dt"].dt.strftime("%Y%m%d").astype(int)
    dim["data"] = dim["data_dt"].dt.strftime("%Y-%m-%d")
    dim["dia"] = dim["data_dt"].dt.day
    dim["mes"] = dim["data_dt"].dt.month
    dim["nome_mes"] = dim["mes"].apply(lambda m: MESES[m - 1])
    dim["num_dia_semana"] = dim["data_dt"].dt.dayofweek + 1  # 1 = segunda
    dim["dia_semana"] = dim["num_dia_semana"].apply(lambda n: DIAS_SEMANA[n - 1])
    dim["fim_de_semana"] = (dim["num_dia_semana"] >= 6).astype(int)
    return dim[["id_data", "data", "dia", "mes", "nome_mes",
                "dia_semana", "num_dia_semana", "fim_de_semana"]]


def montar_dim_operador(vendas: pd.DataFrame) -> pd.DataFrame:
    dim = (vendas[["operador", "turno"]].drop_duplicates()
           .sort_values("operador").reset_index(drop=True))
    dim.insert(0, "id_operador", dim.index + 1)
    return dim


def montar_dim_forma() -> pd.DataFrame:
    dim = pd.DataFrame(FORMAS, columns=["forma_pagamento", "tipo", "como_conferir"])
    dim.insert(0, "id_forma", dim.index + 1)
    return dim


def montar_fato_vendas(vendas, pendencias, dim_operador, dim_forma) -> pd.DataFrame:
    """Uma linha por venda, com o status que a Etapa 2 encontrou."""
    fato = vendas.merge(
        pendencias[["id_venda", "valor_recebido", "motivo"]], on="id_venda", how="left"
    )

    # Status: pendência (cartão/PIX), dinheiro (conferido na gaveta) ou conciliado
    fato["status_conciliacao"] = fato["motivo"].map(STATUS_PENDENCIA)
    eh_dinheiro = fato["forma_pagamento"] == "Dinheiro"
    fato.loc[eh_dinheiro, "status_conciliacao"] = "Dinheiro"
    fato["status_conciliacao"] = fato["status_conciliacao"].fillna("Conciliado")

    # Valor recebido: conciliada recebeu o valor cheio; dinheiro fica vazio (NULL)
    conciliada = fato["status_conciliacao"] == "Conciliado"
    fato.loc[conciliada, "valor_recebido"] = fato.loc[conciliada, "valor"]
    fato.loc[eh_dinheiro, "valor_recebido"] = None
    fato["diferenca"] = (fato["valor_recebido"] - fato["valor"]).fillna(0).round(2)

    # Troca os textos pelas chaves das dimensões
    fato["id_data"] = id_data(fato["data"])
    fato["hora"] = pd.to_datetime(fato["data_hora"]).dt.strftime("%H:%M:%S")
    fato = fato.merge(dim_operador[["id_operador", "operador"]], on="operador")
    fato = fato.merge(dim_forma[["id_forma", "forma_pagamento"]], on="forma_pagamento")

    return fato[["id_venda", "id_data", "id_operador", "id_forma", "hora", "valor",
                 "valor_recebido", "diferenca", "status_conciliacao"]].sort_values("id_venda")


def montar_fato_gaveta(gaveta, dim_operador) -> pd.DataFrame:
    fato = gaveta.merge(dim_operador[["id_operador", "operador"]], on="operador")
    fato["id_data"] = id_data(fato["data"])
    fato = fato.rename(columns={"dinheiro_esperado": "esperado",
                                "dinheiro_em_gaveta": "contado"})
    return fato[["id_data", "id_operador", "turno", "esperado",
                 "contado", "diferenca", "status"]]


def main():
    vendas = pd.read_csv(TRATADOS / "vendas.csv")
    pendencias = pd.read_csv(RESULTADOS / "pendencias.csv")
    gaveta = pd.read_csv(RESULTADOS / "conciliacao_gaveta.csv")

    dim_data = montar_dim_data(vendas)
    dim_operador = montar_dim_operador(vendas)
    dim_forma = montar_dim_forma()
    fato_vendas = montar_fato_vendas(vendas, pendencias, dim_operador, dim_forma)
    fato_gaveta = montar_fato_gaveta(gaveta, dim_operador)

    # Conferência: nenhuma venda pode se perder no caminho
    assert len(fato_vendas) == len(vendas), "Alguma venda se perdeu ao montar a fato!"

    BANCO.parent.mkdir(exist_ok=True)
    with sqlite3.connect(BANCO) as conexao:
        # 1. Cria as tabelas (apaga as antigas, se existirem)
        conexao.executescript(SQL_MODELO.read_text(encoding="utf-8"))

        # 2. Insere os dados. Dimensões primeiro, depois as fatos.
        tabelas = {
            "dim_data": dim_data,
            "dim_operador": dim_operador,
            "dim_forma_pagamento": dim_forma,
            "fato_vendas": fato_vendas,
            "fato_gaveta": fato_gaveta,
        }
        for nome, tabela in tabelas.items():
            tabela.to_sql(nome, conexao, if_exists="append", index=False)
            print(f"{nome:<22} {len(tabela):>5} linhas")

    print(f"\nBanco criado em: {BANCO}")
    print("Para testar as consultas: sqlite3 banco/caixa.db < sql/02_consultas_conciliacao.sql")


if __name__ == "__main__":
    main()
