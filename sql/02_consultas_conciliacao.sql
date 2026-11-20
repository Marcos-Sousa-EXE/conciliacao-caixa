-- =====================================================================
-- Etapa 3 - Consultas de conciliação no modelo estrela
-- =====================================================================
-- Como rodar (depois do python src/carregar_banco.py):
--     sqlite3 -header -column banco/caixa.db < sql/02_consultas_conciliacao.sql
--
-- Lembrete: diferença NEGATIVA = dinheiro que deveria ter entrado e não entrou.
-- Os totais batem com os resultados do src/conciliacao.py (Etapa 2).
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1) Diferença por operador e forma de pagamento
--    Junta as duas fatos: cartão/PIX vêm da fato_vendas e o dinheiro vem
--    da fato_gaveta (só turnos com Falta ou Sobra acima de R$ 1).
--    Mesmo resultado do resultados/resumo_operador.csv.
-- ---------------------------------------------------------------------
SELECT
    o.operador,
    o.turno,
    ROUND(SUM(CASE WHEN d.forma = 'Crédito'  THEN d.diferenca ELSE 0 END), 2) AS credito,
    ROUND(SUM(CASE WHEN d.forma = 'Débito'   THEN d.diferenca ELSE 0 END), 2) AS debito,
    ROUND(SUM(CASE WHEN d.forma = 'PIX'      THEN d.diferenca ELSE 0 END), 2) AS pix,
    ROUND(SUM(CASE WHEN d.forma = 'Dinheiro' THEN d.diferenca ELSE 0 END), 2) AS dinheiro,
    ROUND(SUM(d.diferenca), 2) AS total
FROM (
    -- diferenças de cartão e PIX, venda a venda
    SELECT v.id_operador, f.forma_pagamento AS forma, v.diferenca
    FROM fato_vendas v
    JOIN dim_forma_pagamento f ON f.id_forma = v.id_forma
    WHERE f.forma_pagamento <> 'Dinheiro'

    UNION ALL

    -- diferenças da gaveta de dinheiro, turno a turno
    SELECT g.id_operador, 'Dinheiro' AS forma, g.diferenca
    FROM fato_gaveta g
    WHERE g.status <> 'OK'
) AS d
JOIN dim_operador o ON o.id_operador = d.id_operador
GROUP BY o.operador, o.turno
ORDER BY total;


-- ---------------------------------------------------------------------
-- 2) Diferença por dia da semana
--    Existe um dia da semana em que o caixa "fura" mais?
--    Começa pela dim_data com LEFT JOIN para contar TODOS os dias do mês,
--    inclusive os dias sem nenhuma diferença (senão a média sairia errada).
-- ---------------------------------------------------------------------
SELECT
    dt.dia_semana,
    COUNT(*)                               AS qtd_dias_no_mes,
    SUM(COALESCE(d.ocorrencias, 0))        AS ocorrencias,
    ROUND(SUM(COALESCE(d.diferenca, 0)), 2) AS diferenca_total,
    ROUND(SUM(COALESCE(d.diferenca, 0)) / COUNT(*), 2) AS diferenca_media_por_dia
FROM dim_data dt
LEFT JOIN (
    -- diferença de cada dia (cartão/PIX + gaveta)
    SELECT id_data, COUNT(*) AS ocorrencias, SUM(diferenca) AS diferenca
    FROM (
        SELECT id_data, diferenca FROM fato_vendas WHERE diferenca <> 0
        UNION ALL
        SELECT id_data, diferenca FROM fato_gaveta WHERE status <> 'OK'
    )
    GROUP BY id_data
) AS d ON d.id_data = dt.id_data
GROUP BY dt.dia_semana, dt.num_dia_semana
ORDER BY dt.num_dia_semana;


-- ---------------------------------------------------------------------
-- 3) Taxa de conciliação por forma de pagamento
--    Cartão e PIX: % de vendas confirmadas na maquininha / no banco.
--    Dinheiro: % de turnos em que a gaveta bateu (status OK).
-- ---------------------------------------------------------------------
SELECT
    f.forma_pagamento,
    COUNT(*) AS qtd_vendas,
    SUM(CASE WHEN v.status_conciliacao = 'Conciliado' THEN 1 ELSE 0 END) AS conciliadas,
    COUNT(*) - SUM(CASE WHEN v.status_conciliacao = 'Conciliado' THEN 1 ELSE 0 END) AS pendentes,
    ROUND(100.0 * SUM(CASE WHEN v.status_conciliacao = 'Conciliado' THEN 1 ELSE 0 END)
          / COUNT(*), 2) AS taxa_conciliacao_pct
FROM fato_vendas v
JOIN dim_forma_pagamento f ON f.id_forma = v.id_forma
WHERE f.forma_pagamento <> 'Dinheiro'
GROUP BY f.forma_pagamento

UNION ALL

SELECT
    'Dinheiro (por turno)',
    COUNT(*),
    SUM(CASE WHEN status = 'OK' THEN 1 ELSE 0 END),
    SUM(CASE WHEN status <> 'OK' THEN 1 ELSE 0 END),
    ROUND(100.0 * SUM(CASE WHEN status = 'OK' THEN 1 ELSE 0 END) / COUNT(*), 2)
FROM fato_gaveta;


-- ---------------------------------------------------------------------
-- 4) Ranking dos turnos com falta na gaveta (da maior falta para a menor)
--    RANK() numera as linhas na ordem escolhida (função de janela).
-- ---------------------------------------------------------------------
SELECT
    RANK() OVER (ORDER BY g.diferenca) AS posicao,
    dt.data,
    dt.dia_semana,
    g.turno,
    o.operador,
    g.esperado,
    g.contado,
    g.diferenca
FROM fato_gaveta g
JOIN dim_data dt    ON dt.id_data = g.id_data
JOIN dim_operador o ON o.id_operador = g.id_operador
WHERE g.status = 'Falta'
ORDER BY posicao;


-- ---------------------------------------------------------------------
-- 5) Vendas pendentes acima de R$ 100
--    Lista de prioridade para o supervisor investigar primeiro.
-- ---------------------------------------------------------------------
SELECT
    v.id_venda,
    dt.data,
    v.hora,
    o.operador,
    f.forma_pagamento,
    v.valor,
    v.status_conciliacao
FROM fato_vendas v
JOIN dim_data dt            ON dt.id_data = v.id_data
JOIN dim_operador o         ON o.id_operador = v.id_operador
JOIN dim_forma_pagamento f  ON f.id_forma = v.id_forma
WHERE v.status_conciliacao NOT IN ('Conciliado', 'Dinheiro')
  AND v.valor > 100
ORDER BY v.valor DESC;


-- ---------------------------------------------------------------------
-- 6) Participação de cada operador na diferença total (com CTE)
--    CTE = "WITH nome AS (...)": uma consulta com nome, usada como se
--    fosse uma tabela temporária. Deixa a consulta final mais fácil de ler.
-- ---------------------------------------------------------------------
WITH faturamento AS (
    -- quanto cada operador vendeu no mês
    SELECT id_operador, SUM(valor) AS vendido
    FROM fato_vendas
    GROUP BY id_operador
),
diferencas AS (
    -- quanto faltou para cada operador (cartão + PIX + gaveta)
    SELECT id_operador, SUM(diferenca) AS diferenca
    FROM (
        SELECT id_operador, diferenca FROM fato_vendas
        UNION ALL
        SELECT id_operador, diferenca FROM fato_gaveta WHERE status <> 'OK'
    )
    GROUP BY id_operador
),
total AS (
    SELECT SUM(diferenca) AS diferenca_total FROM diferencas
)
SELECT
    o.operador,
    ROUND(fa.vendido, 2)                                    AS vendido,
    ROUND(di.diferenca, 2)                                  AS diferenca,
    ROUND(100.0 * di.diferenca / fa.vendido, 2)             AS pct_do_que_vendeu,
    ROUND(100.0 * di.diferenca / t.diferenca_total, 1)      AS pct_da_diferenca_total
FROM dim_operador o
JOIN faturamento fa ON fa.id_operador = o.id_operador
JOIN diferencas  di ON di.id_operador = o.id_operador
CROSS JOIN total t
ORDER BY di.diferenca;
