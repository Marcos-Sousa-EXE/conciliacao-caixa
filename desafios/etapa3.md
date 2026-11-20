# Desafio da Etapa 3

Desafio para eu resolver sozinho, sem olhar a resposta pronta, e treinar SQL
para entrevistas.

## A pergunta

> **Qual operador tem o maior tíquete médio em vendas PIX?**
> E esse operador também é o que mais tem PIX não recebido?

Tíquete médio = valor total vendido ÷ quantidade de vendas.

O resultado deve ter uma linha por operador, com as colunas:

| operador | qtd_vendas_pix | total_pix | ticket_medio | qtd_pix_nao_recebido |
|---|---|---|---|---|

ordenado do maior tíquete médio para o menor.

## Dicas

1. A consulta começa pela `fato_vendas`. Quais dimensões preciso juntar para ter
   o **nome** do operador e a **forma de pagamento** em texto?
2. O filtro de PIX vai no `WHERE`, usando a coluna da `dim_forma_pagamento`.
3. `AVG(valor)` faz o tíquete médio direto, mas tente também com `SUM` ÷ `COUNT`
   e confira se dá o mesmo número. Use `ROUND(..., 2)`.
4. Para contar só os PIX não recebidos dentro do mesmo `GROUP BY`, lembre do
   truque `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` usado na consulta 3 do
   `sql/02_consultas_conciliacao.sql`.
5. Para conferir: a soma de `qtd_vendas_pix` dos 4 operadores precisa dar o total
   de vendas PIX (consulta 3), e a soma de `qtd_pix_nao_recebido` precisa dar 12.

## Extra (se sobrar tempo)

- Repetir a mesma análise para **Crédito**, trocando só o filtro.
- Transformar a consulta em uma CTE e mostrar só o operador campeão.
- Pergunta para a entrevista: *por que eu filtro pela dimensão e não escrevo o
  texto "PIX" direto na tabela fato?*

Quando resolver, salvar a consulta em `sql/03_desafio.sql`.
