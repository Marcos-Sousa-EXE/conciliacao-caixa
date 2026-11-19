"""
Etapa 1 - Limpeza e padronização dos dados brutos.

Problemas tratados (os mesmos que aparecem nos exports reais de PDV e banco):
- Datas em formatos diferentes (31/10/2026, 2026-10-31, 31-10-2026)
- Valores como texto: "R$ 1.234,56", "1234,56" e "1234.56"
- Nome do operador digitado de jeitos diferentes ("ANA PAULA", "ana  paula")
  e abreviado ("Bruno C.")
- Forma de pagamento sem padrão ("CREDITO", "Cartão Crédito", "credito")
- Vendas exportadas em duplicidade

Saída: arquivos limpos em dados/tratados/ e um relatório de qualidade dos dados.

Uso:  python src/limpeza.py
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent / "dados"
BRUTOS, TRATADOS = PASTA / "brutos", PASTA / "tratados"

# Cadastro oficial: abreviações conhecidas -> nome correto
APELIDOS_OPERADOR = {
    "bruno c": "Bruno Costa",
    "diego m": "Diego Martins",
}

FORMAS_PAGAMENTO = {
    "credito": "Crédito",
    "cartao credito": "Crédito",
    "debito": "Débito",
    "cartao debito": "Débito",
    "pix": "PIX",
    "dinheiro": "Dinheiro",
    "especie": "Dinheiro",
}


# ---------------------------------------------------------------------------
# Funções de padronização (cada uma resolve um tipo de sujeira)
# ---------------------------------------------------------------------------

def sem_acento(texto: str) -> str:
    """'Crédito' -> 'Credito'. Ajuda a comparar textos digitados de formas diferentes."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def chave_texto(texto: str) -> str:
    """Minúsculo, sem acento, sem ponto e com espaços simples: ' ANA  Paula ' -> 'ana paula'."""
    texto = sem_acento(str(texto)).lower().replace(".", "")
    return re.sub(r"\s+", " ", texto).strip()


def converter_valor(valor) -> float:
    """Converte 'R$ 1.234,56', '1234,56' ou '1234.56' para 1234.56."""
    texto = str(valor).replace("R$", "").strip()
    if "," in texto:  # formato brasileiro: ponto = milhar, vírgula = decimal
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def converter_data(serie: pd.Series) -> pd.Series:
    """Aceita dd/mm/aaaa, aaaa-mm-dd e dd-mm-aaaa (com ou sem hora)."""
    formatos = ["%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y"]
    resultado = pd.Series(pd.NaT, index=serie.index)
    for fmt in formatos:
        faltando = resultado.isna()
        resultado[faltando] = pd.to_datetime(serie[faltando], format=fmt, errors="coerce")
    return resultado


def padronizar_operador(nome: str) -> str:
    chave = chave_texto(nome)
    if chave in APELIDOS_OPERADOR:
        return APELIDOS_OPERADOR[chave]
    return chave.title()


def padronizar_forma(forma: str) -> str:
    return FORMAS_PAGAMENTO.get(chave_texto(forma), "Não identificado")


# ---------------------------------------------------------------------------
# Limpeza de cada arquivo
# ---------------------------------------------------------------------------

def limpar_vendas(relatorio: list) -> pd.DataFrame:
    df = pd.read_csv(BRUTOS / "vendas_pdv.csv", sep=";", dtype=str)
    total = len(df)

    duplicadas = df.duplicated().sum()
    df = df.drop_duplicates()

    variacoes_operador = df["operador"].nunique()
    variacoes_forma = df["forma_pagamento"].nunique()

    df["id_venda"] = df["id_venda"].astype(int)
    df["data_hora"] = converter_data(df["data_hora"])
    df["valor"] = df["valor"].apply(converter_valor)
    df["operador"] = df["operador"].apply(padronizar_operador)
    df["forma_pagamento"] = df["forma_pagamento"].apply(padronizar_forma)
    df["data"] = df["data_hora"].dt.date
    df["turno"] = df["data_hora"].dt.hour.map(lambda h: "Manhã" if h < 14 else "Noite")

    relatorio += [
        f"Vendas brutas: {total} linhas",
        f"  - {duplicadas} vendas duplicadas removidas",
        f"  - {variacoes_operador} grafias de operador -> {df['operador'].nunique()} operadores",
        f"  - {variacoes_forma} grafias de forma de pagamento -> {df['forma_pagamento'].nunique()} formas",
        f"  - {df['data_hora'].isna().sum()} datas que não puderam ser lidas",
        f"Vendas limpas: {len(df)} linhas",
    ]
    return df.sort_values("data_hora")


def limpar_maquininha(relatorio: list) -> pd.DataFrame:
    df = pd.read_csv(BRUTOS / "extrato_maquininha.csv", dtype=str)
    df["data_transacao"] = pd.to_datetime(df["data_transacao"])
    df["valor_bruto"] = df["valor_bruto"].astype(float)
    df["modalidade"] = df["modalidade"].map({"CREDITO": "Crédito", "DEBITO": "Débito"})
    df["id_venda_pdv"] = df["id_venda_pdv"].astype(int)
    relatorio.append(f"Extrato da maquininha: {len(df)} transações")
    return df


def limpar_pix(relatorio: list) -> pd.DataFrame:
    df = pd.read_csv(BRUTOS / "extrato_pix.csv", sep=";", dtype=str)
    df["data_hora"] = converter_data(df["data_hora"])
    df["valor"] = df["valor"].apply(converter_valor)
    # O número da venda vem escrito dentro da descrição: "PIX RECEBIDO - VENDA 50010"
    df["id_venda_pdv"] = df["descricao"].str.extract(r"VENDA (\d+)")[0].astype(int)
    relatorio.append(f"Extrato PIX: {len(df)} recebimentos")
    return df


def limpar_fechamento(relatorio: list) -> pd.DataFrame:
    df = pd.read_csv(BRUTOS / "fechamento_dinheiro.csv", sep=";", dtype=str)
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y").dt.date
    df["fundo_de_troco"] = df["fundo_de_troco"].apply(converter_valor)
    df["valor_contado"] = df["valor_contado"].apply(converter_valor)
    df["dinheiro_em_gaveta"] = (df["valor_contado"] - df["fundo_de_troco"]).round(2)
    relatorio.append(f"Fechamentos de caixa: {len(df)} turnos")
    return df


def main():
    TRATADOS.mkdir(parents=True, exist_ok=True)
    relatorio = ["RELATÓRIO DE QUALIDADE DOS DADOS", "=" * 34]

    limpar_vendas(relatorio).to_csv(TRATADOS / "vendas.csv", index=False)
    limpar_maquininha(relatorio).to_csv(TRATADOS / "maquininha.csv", index=False)
    limpar_pix(relatorio).to_csv(TRATADOS / "pix.csv", index=False)
    limpar_fechamento(relatorio).to_csv(TRATADOS / "fechamento.csv", index=False)

    texto = "\n".join(relatorio)
    (TRATADOS / "relatorio_qualidade.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print(f"\nArquivos limpos salvos em: {TRATADOS}")


if __name__ == "__main__":
    main()
