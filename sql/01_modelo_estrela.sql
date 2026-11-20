-- =====================================================================
-- Etapa 3 - Modelo estrela (Star Schema) da conciliação de caixa
-- =====================================================================
--
-- O modelo estrela separa os dados em dois tipos de tabela:
--
-- TABELAS DIMENSÃO (dim_*)
--   Descrevem o "quem, quando e como" de cada acontecimento.
--   São tabelas pequenas, com poucas linhas e textos fáceis de ler
--   (nome do operador, dia da semana, forma de pagamento...).
--   É por elas que a gente FILTRA e AGRUPA os relatórios.
--
-- TABELAS FATO (fato_*)
--   Guardam os acontecimentos em si, com os NÚMEROS (valores em R$).
--   Têm muitas linhas e quase nenhum texto: no lugar do nome do operador,
--   guardam só a chave (id_operador) que aponta para a dimensão.
--
-- Desenhando, a fato fica no meio e as dimensões em volta, como uma
-- estrela. É o mesmo formato que o Power BI usa (Etapa 5).
--
-- Este arquivo é executado pelo src/carregar_banco.py.
-- =====================================================================

DROP TABLE IF EXISTS fato_vendas;
DROP TABLE IF EXISTS fato_gaveta;
DROP TABLE IF EXISTS dim_data;
DROP TABLE IF EXISTS dim_operador;
DROP TABLE IF EXISTS dim_forma_pagamento;


-- ---------------------------------------------------------------------
-- DIMENSÃO: calendário (uma linha por dia de outubro/2026)
-- ---------------------------------------------------------------------
CREATE TABLE dim_data (
    id_data        INTEGER PRIMARY KEY,   -- formato AAAAMMDD, ex.: 20261031
    data           TEXT    NOT NULL,      -- ex.: 2026-10-31
    dia            INTEGER NOT NULL,      -- 1 a 31
    mes            INTEGER NOT NULL,      -- 1 a 12
    nome_mes       TEXT    NOT NULL,      -- ex.: Outubro
    dia_semana     TEXT    NOT NULL,      -- ex.: Sábado
    num_dia_semana INTEGER NOT NULL,      -- 1 = Segunda ... 7 = Domingo (para ordenar)
    fim_de_semana  INTEGER NOT NULL       -- 1 = sábado ou domingo, 0 = dia útil
);


-- ---------------------------------------------------------------------
-- DIMENSÃO: operadores de caixa
-- ---------------------------------------------------------------------
CREATE TABLE dim_operador (
    id_operador INTEGER PRIMARY KEY,
    operador    TEXT NOT NULL UNIQUE,     -- nome padronizado na Etapa 1
    turno       TEXT NOT NULL             -- Manhã ou Noite
);


-- ---------------------------------------------------------------------
-- DIMENSÃO: formas de pagamento
-- ---------------------------------------------------------------------
CREATE TABLE dim_forma_pagamento (
    id_forma        INTEGER PRIMARY KEY,
    forma_pagamento TEXT NOT NULL UNIQUE, -- Crédito, Débito, PIX, Dinheiro
    tipo            TEXT NOT NULL,        -- Cartão, PIX ou Dinheiro
    como_conferir   TEXT NOT NULL         -- onde a venda é confirmada
);


-- ---------------------------------------------------------------------
-- FATO: vendas (uma linha por venda registrada no PDV)
-- ---------------------------------------------------------------------
CREATE TABLE fato_vendas (
    id_venda        INTEGER PRIMARY KEY,  -- número da venda no PDV
    id_data         INTEGER NOT NULL REFERENCES dim_data(id_data),
    id_operador     INTEGER NOT NULL REFERENCES dim_operador(id_operador),
    id_forma        INTEGER NOT NULL REFERENCES dim_forma_pagamento(id_forma),
    hora            TEXT    NOT NULL,     -- ex.: 14:32:00
    valor           REAL    NOT NULL,     -- valor da venda no PDV
    valor_recebido  REAL,                 -- o que entrou de fato (NULL para dinheiro,
                                          -- que é conferido por turno na fato_gaveta)
    diferenca       REAL    NOT NULL,     -- valor_recebido - valor (negativo = perda)
    status_conciliacao TEXT NOT NULL      -- Conciliado / Não consta na maquininha /
                                          -- Valor diferente na maquininha /
                                          -- PIX não recebido / Dinheiro
);


-- ---------------------------------------------------------------------
-- FATO: fechamento da gaveta (uma linha por operador por turno por dia)
-- ---------------------------------------------------------------------
CREATE TABLE fato_gaveta (
    id_data     INTEGER NOT NULL REFERENCES dim_data(id_data),
    id_operador INTEGER NOT NULL REFERENCES dim_operador(id_operador),
    turno       TEXT    NOT NULL,
    esperado    REAL    NOT NULL,         -- soma das vendas em dinheiro do turno
    contado     REAL    NOT NULL,         -- dinheiro na gaveta (já sem o fundo de troco)
    diferenca   REAL    NOT NULL,         -- contado - esperado (negativo = falta)
    status      TEXT    NOT NULL,         -- OK (até R$ 1 de diferença), Falta ou Sobra
    PRIMARY KEY (id_data, id_operador, turno)
);
