import sqlite3

import coleta


def test_linhas_da_api_converte_timestamp():
    resp = {"items": [{"timestamp": "2026110100", "views": 292}, {"timestamp": "2026110200", "views": 284}]}
    assert coleta.linhas_da_api("Nubank", resp) == [("Nubank", "2026-11-01", 292), ("Nubank", "2026-11-02", 284)]


def test_banco_removido_do_csv_sai_do_banco(tmp_path, monkeypatch):
    (tmp_path / "bancos.csv").write_text("banco,grupo,artigo\nA,G,A\n", encoding="utf-8")
    (tmp_path / "schema.sql").write_text((coleta.RAIZ / "schema.sql").read_text(encoding="utf-8"), encoding="utf-8")
    db = tmp_path / "data" / "t.db"
    db.parent.mkdir()
    with sqlite3.connect(db) as con:  # banco de dados com um banco que saiu da lista
        con.executescript((tmp_path / "schema.sql").read_text(encoding="utf-8"))
        con.execute("INSERT INTO bancos VALUES ('Velho', 'Velho', 'G')")
        con.execute("INSERT INTO pageviews VALUES ('Velho', '2026-01-01', 5)")
    monkeypatch.setattr(coleta, "RAIZ", tmp_path)
    monkeypatch.setattr(coleta, "DB", db)
    monkeypatch.setattr(coleta, "baixar", lambda url: {"items": [{"timestamp": "2026010100", "views": 7}]})
    monkeypatch.setattr(coleta.time, "sleep", lambda s: None)
    coleta.coletar()
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT artigo FROM bancos").fetchall() == [("A",)]
        assert con.execute("SELECT artigo, views FROM pageviews").fetchall() == [("A", 7)]
