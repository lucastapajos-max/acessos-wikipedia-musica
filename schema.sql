CREATE TABLE IF NOT EXISTS bancos (
    artigo TEXT PRIMARY KEY,    -- título do verbete na Wikipédia pt
    banco  TEXT NOT NULL,
    grupo  TEXT NOT NULL        -- Digital ou Tradicional, agrupamento do projeto
);
CREATE TABLE IF NOT EXISTS pageviews (
    artigo TEXT NOT NULL REFERENCES bancos(artigo),
    data   TEXT NOT NULL,       -- AAAA-MM-DD
    views  INTEGER NOT NULL,
    PRIMARY KEY (artigo, data)
);
