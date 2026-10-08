"""Banco local (SQLite): quem recebeu o quê, bloqueios e andamento da conversa."""
import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS envios (
  email TEXT NOT NULL, etapa INTEGER NOT NULL, marca TEXT, assunto TEXT,
  status TEXT NOT NULL,             -- enviando | enviado | erro
  dia TEXT, enviado_em TEXT, message_id TEXT, erro TEXT,
  PRIMARY KEY (email, etapa)
);
CREATE TABLE IF NOT EXISTS bloqueio (email TEXT PRIMARY KEY, motivo TEXT, em TEXT);
CREATE TABLE IF NOT EXISTS relacao (email TEXT PRIMARY KEY, status TEXT, em TEXT);  -- respondeu | negociacao | bounce
"""


class Store:
    def __init__(self, caminho: Path | str):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(caminho))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(ESQUEMA)

    # --- envios ---
    def envio(self, email, etapa):
        return self.db.execute("SELECT * FROM envios WHERE email=? AND etapa=?", (email, etapa)).fetchone()

    def iniciar(self, email, etapa, marca, assunto, dia):
        """Marca 'enviando' ANTES de mandar: se o programa cair no meio, nunca reenvia por engano."""
        self.db.execute(
            "INSERT OR REPLACE INTO envios(email,etapa,marca,assunto,status,dia) VALUES(?,?,?,?, 'enviando', ?)",
            (email, etapa, marca, assunto, dia),
        )
        self.db.commit()

    def concluir(self, email, etapa, ok, agora_iso, message_id="", erro=""):
        self.db.execute(
            "UPDATE envios SET status=?, enviado_em=?, message_id=?, erro=? WHERE email=? AND etapa=?",
            ("enviado" if ok else "erro", agora_iso, message_id, erro, email, etapa),
        )
        self.db.commit()

    def enviados_no_dia(self, dia):
        return self.db.execute("SELECT COUNT(*) FROM envios WHERE dia=? AND status='enviado'", (dia,)).fetchone()[0]

    def todos_enviados(self):
        return [r["email"] for r in self.db.execute("SELECT DISTINCT email FROM envios WHERE status='enviado'")]

    # --- bloqueio / relação ---
    def bloquear(self, email, motivo, em):
        self.db.execute("INSERT OR REPLACE INTO bloqueio VALUES(?,?,?)", (email.lower(), motivo, em))
        self.db.commit()

    def bloqueado(self, email):
        return self.db.execute("SELECT 1 FROM bloqueio WHERE email=?", (email,)).fetchone() is not None

    def definir_relacao(self, email, status, em):
        self.db.execute("INSERT OR REPLACE INTO relacao VALUES(?,?,?)", (email.lower(), status, em))
        self.db.commit()

    def relacao(self, email):
        r = self.db.execute("SELECT status FROM relacao WHERE email=?", (email,)).fetchone()
        return r["status"] if r else None

    # --- para a planilha ---
    def status_planilha(self, email):
        """(Status, Enviado em, Observações) ou None se não há nada a escrever."""
        if self.bloqueado(email):
            return ("Descadastrado", "", "Pediu para sair / bloqueado")
        rel = self.relacao(email)
        e1, e2 = self.envio(email, 1), self.envio(email, 2)
        ultimo = e2 or e1
        quando = (ultimo["enviado_em"] or "")[:16].replace("T", " ") if ultimo else ""
        if rel == "negociacao":
            return ("Em negociação", quando, "")
        if rel == "respondeu":
            return ("Respondeu", quando, "")
        if rel == "bounce":
            return ("Erro", quando, "E-mail não entregue (bounce)")
        if not ultimo:
            return None
        if ultimo["status"] == "erro":
            return ("Erro", quando, ultimo["erro"] or "")
        if ultimo["status"] == "enviando":
            return ("Verificar", quando, "Envio interrompido: confira a caixa de Enviados")
        return ("Follow-up enviado" if ultimo["etapa"] == 2 else "Enviado", quando, "")
