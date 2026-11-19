"""
Gera os dados FICTÍCIOS do projeto, imitando os arquivos que uma loja de varejo
recebe todo dia:

- vendas_pdv.csv           -> export do sistema do caixa (PDV)
- extrato_maquininha.csv   -> extrato da operadora de cartão
- extrato_pix.csv          -> extrato de PIX do banco
- fechamento_dinheiro.csv  -> contagem do dinheiro na gaveta no fim do turno

Os arquivos saem "sujos" de propósito, como na vida real: datas em formatos
diferentes, valores com "R$" e vírgula, nomes de operador escritos de jeitos
diferentes, linhas duplicadas e transações que não aparecem nos extratos.

Rodar só uma vez:  python scripts/gerar_dados.py
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(2026)
PASTA = Path(__file__).resolve().parent.parent / "dados" / "brutos"
PASTA.mkdir(parents=True, exist_ok=True)

# Operadores e as várias formas como o nome aparece digitado no PDV
OPERADORES = {
    "Ana Paula": ["Ana Paula", "ANA PAULA", "ana paula", "Ana  Paula"],
    "Bruno Costa": ["Bruno Costa", "BRUNO COSTA", "Bruno C."],
    "Camila Reis": ["Camila Reis", "CAMILA REIS", "camila reis"],
    "Diego Martins": ["Diego Martins", "DIEGO MARTINS", "Diego M."],
}
TURNOS = {"Manhã": (8, 14), "Noite": (14, 22)}
ESCALA = {  # quem trabalha em cada turno
    "Manhã": ["Ana Paula", "Bruno Costa"],
    "Noite": ["Camila Reis", "Diego Martins"],
}
FORMAS = {
    "Crédito": ["Crédito", "CREDITO", "Cartão Crédito", "credito"],
    "Débito": ["Débito", "DEBITO", "Cartão Débito", "debito"],
    "PIX": ["PIX", "Pix", "pix"],
    "Dinheiro": ["Dinheiro", "DINHEIRO", "dinheiro", "Espécie"],
}
PESO_FORMAS = [0.38, 0.27, 0.22, 0.13]


def formatar_data(dt: datetime) -> str:
    """O PDV exporta datas em formatos diferentes dependendo da versão."""
    return random.choice([
        dt.strftime("%d/%m/%Y %H:%M"),
        dt.strftime("%Y-%m-%d %H:%M:%S"),
        dt.strftime("%d-%m-%Y %H:%M"),
    ])


def formatar_valor(v: float) -> str:
    """Valores às vezes vêm com R$, às vezes com vírgula decimal."""
    br = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return random.choice([br, f"R$ {br}", f"{v:.2f}"])


vendas, maquininha, pix, fechamento = [], [], [], []
id_venda = 50001
inicio = datetime(2026, 10, 1)

for dia in range(31):
    data = inicio + timedelta(days=dia)
    for turno, (h_ini, h_fim) in TURNOS.items():
        for operador in ESCALA[turno]:
            dinheiro_turno = 0.0
            for _ in range(random.randint(14, 24)):
                hora = data + timedelta(hours=random.uniform(h_ini, h_fim))
                forma = random.choices(list(FORMAS), PESO_FORMAS)[0]
                valor = round(random.lognormvariate(4.3, 0.7), 2)  # tíquete médio ~R$ 90

                vendas.append({
                    "id_venda": id_venda,
                    "data_hora": formatar_data(hora),
                    "operador": random.choice(OPERADORES[operador]),
                    "forma_pagamento": random.choice(FORMAS[forma]),
                    "valor": formatar_valor(valor),
                })

                if forma in ("Crédito", "Débito"):
                    # ~1,5% das vendas no cartão não aparecem no extrato
                    # (transação negada que o operador registrou como paga)
                    if random.random() > 0.015:
                        maquininha.append({
                            "nsu": f"{random.randint(10**8, 10**9 - 1)}",
                            "data_transacao": hora.strftime("%Y-%m-%d %H:%M:%S"),
                            "modalidade": "CREDITO" if forma == "Crédito" else "DEBITO",
                            "valor_bruto": f"{valor:.2f}",
                            "id_venda_pdv": id_venda,
                        })
                elif forma == "PIX":
                    # ~2% dos PIX não caíram (cliente mostrou comprovante falso/agendado)
                    if random.random() > 0.02:
                        pix.append({
                            "e2e_id": f"E{random.randint(10**15, 10**16 - 1)}",
                            "data_hora": hora.strftime("%d/%m/%Y %H:%M"),
                            "valor": formatar_valor(valor).replace("R$ ", ""),
                            "descricao": f"PIX RECEBIDO - VENDA {id_venda}",
                        })
                else:
                    dinheiro_turno += valor

                id_venda += 1

            # Contagem da gaveta no fim do turno. Diferenças pequenas são normais
            # (troco), mas um operador do turno da noite tem faltas recorrentes.
            diferenca = random.choice([0, 0, 0, 0, -0.05, 0.10, -0.50])
            if operador == "Diego Martins" and random.random() < 0.45:
                diferenca = -round(random.uniform(15, 80), 2)
            fechamento.append({
                "data": data.strftime("%d/%m/%Y"),
                "turno": turno,
                "operador": operador,
                "fundo_de_troco": "200,00",
                "valor_contado": formatar_valor(200 + dinheiro_turno + diferenca).replace("R$ ", ""),
            })

# Sujeira extra: algumas vendas exportadas em duplicidade
duplicadas = random.sample(vendas, 12)
vendas.extend(duplicadas)
random.shuffle(vendas)

pd.DataFrame(vendas).to_csv(PASTA / "vendas_pdv.csv", index=False, sep=";", encoding="utf-8")
pd.DataFrame(maquininha).to_csv(PASTA / "extrato_maquininha.csv", index=False)
pd.DataFrame(pix).to_csv(PASTA / "extrato_pix.csv", index=False, sep=";")
pd.DataFrame(fechamento).to_csv(PASTA / "fechamento_dinheiro.csv", index=False, sep=";")

print(f"Vendas: {len(vendas)} | Maquininha: {len(maquininha)} | PIX: {len(pix)} | Fechamentos: {len(fechamento)}")
