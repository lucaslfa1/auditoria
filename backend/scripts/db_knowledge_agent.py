from typing import Any
"""
DB Knowledge Agent — Extrai conhecimento do banco de dados e documentos
do projeto para gerar documentos Markdown otimizados para RAG.

Uso:
    python -m scripts.db_knowledge_agent
"""

import logging
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path

# Ensure backend is on sys.path so db.connection can be imported
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from db.connection import get_connection  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DEFAULT_OUTPUT_DIR = _BACKEND_DIR / "data" / "rag_training"
_SCORING_RULES_PATH = _BACKEND_DIR / "db" / "scoring_rules.yaml"
_INSTRUCOES_DIR = _BACKEND_DIR.parent / "instrucoes"
_REFERENCES_DIR = _BACKEND_DIR.parent / "docs" / "references"
_AUDITORIA_REFERENCES_DIR = _REFERENCES_DIR / "auditoria"
_OPERACIONAL_REFERENCES_DIR = _REFERENCES_DIR / "operacional"
_RAG_SOURCES_DIR = _BACKEND_DIR.parent / "rag" / "sources"


class DBKnowledgeAgent:
    """Extrai conhecimento estruturado do banco e gera docs para RAG."""

    def __init__(
        self,
        output_dir: str | Path | None = None,
    ):
        self.output_dir = Path(output_dir or _DEFAULT_OUTPUT_DIR)
        self._generated_files: list[str] = []
        self._timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> list[str]:
        """Executa todas as extrações e retorna lista de arquivos gerados."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("DB Knowledge Agent iniciando — out=%s", self.output_dir)

        self._extract_colaboradores()
        self._extract_supervisores()
        self._extract_setores()
        self._extract_criterios()
        self._extract_configuracoes()
        self._extract_usuarios()
        self._extract_schema()
        self._extract_estatisticas()
        self._extract_regras_negocio()
        self._write_index()

        logger.info("DB Knowledge Agent concluído — %d arquivos gerados", len(self._generated_files))
        return self._generated_files

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _conn(self) -> Any:
        return get_connection()

    def _header(self, title: str) -> str:
        return (
            f"# {title}\n\n"
            f"> Documento gerado automaticamente pelo DB Knowledge Agent.\n"
            f"> Banco: PostgreSQL (local) | Data: {self._timestamp}\n\n"
        )

    def _save(self, filename: str, content: str) -> None:
        path = self.output_dir / filename
        path.write_text(content, encoding="utf-8")
        self._generated_files.append(filename)
        logger.info("  → %s (%d bytes)", filename, len(content))

    # ------------------------------------------------------------------
    # Extractors
    # ------------------------------------------------------------------
    def _extract_colaboradores(self) -> None:
        conn = self._conn()
        c = conn.cursor()

        c.execute("""
            SELECT id, nome, supervisor, setor, escala, status, matricula,
                   id_weon, id_huawei, auditavel
            FROM colaboradores
            ORDER BY setor, supervisor, nome
        """)
        rows = c.fetchall()
        conn.close()

        lines = [self._header("Colaboradores")]
        lines.append(f"Total de colaboradores cadastrados: {len(rows)}.\n\n")

        # Group by setor
        by_setor: dict[str, list] = {}
        for r in rows:
            setor = r["setor"] or "Sem setor"
            by_setor.setdefault(setor, []).append(r)

        for setor in sorted(by_setor.keys()):
            members = by_setor[setor]
            lines.append(f"## Setor: {setor} ({len(members)} colaboradores)\n\n")
            for r in members:
                sup = r["supervisor"] or "sem supervisor"
                escala = r["escala"] or "sem escala"
                status = r["status"] or "?"
                auditavel = "auditável" if r["auditavel"] else "não auditável"
                lines.append(
                    f"- **{r['nome']}** — supervisor: {sup}, "
                    f"escala: {escala}, status: {status}, {auditavel}"
                )
                ids = []
                if r["matricula"]:
                    ids.append(f"matrícula {r['matricula']}")
                if r["id_weon"]:
                    ids.append(f"ID WEON {r['id_weon']}")
                if r["id_huawei"]:
                    ids.append(f"ID Huawei {r['id_huawei']}")
                if ids:
                    lines[-1] += f" ({', '.join(ids)})"
                lines.append("")
            lines.append("")

        self._save("colaboradores.md", "\n".join(lines))

    def _extract_supervisores(self) -> None:
        conn = self._conn()
        c = conn.cursor()

        c.execute("""
            SELECT supervisor, setor, escala, COUNT(*) as cnt
            FROM colaboradores
            WHERE supervisor IS NOT NULL AND supervisor != ''
            AND auditavel = 1
            GROUP BY supervisor, setor, escala
            ORDER BY supervisor, setor
        """)
        rows = c.fetchall()
        conn.close()

        by_sup: dict[str, list] = {}
        for r in rows:
            by_sup.setdefault(r["supervisor"], []).append(r)

        lines = [self._header("Supervisores e suas Equipes")]

        for sup in sorted(by_sup.keys()):
            entries = by_sup[sup]
            total = sum(e["cnt"] for e in entries)
            setores = sorted(set(e["setor"] or "?" for e in entries))
            escalas = sorted(set(e["escala"] or "?" for e in entries))
            lines.append(f"## {sup}\n")
            lines.append(f"- Total de operadores auditáveis: {total}")
            lines.append(f"- Setores: {', '.join(setores)}")
            lines.append(f"- Escalas: {', '.join(escalas)}")
            lines.append("")
            for e in entries:
                lines.append(
                    f"  - {e['setor'] or '?'} / {e['escala'] or '?'}: {e['cnt']} operadores"
                )
            lines.append("")

        self._save("supervisores.md", "\n".join(lines))

    def _extract_setores(self) -> None:
        conn = self._conn()
        c = conn.cursor()

        # Setores do banco (audit_sectors)
        c.execute("SELECT id, label, description FROM audit_sectors ORDER BY id")
        sectors = c.fetchall()

        # Escalas usadas
        c.execute("""
            SELECT escala, COUNT(*) as cnt,
                   SUM(CASE WHEN auditavel = 1 THEN 1 ELSE 0 END) as auditaveis
            FROM colaboradores
            WHERE escala IS NOT NULL AND escala != ''
            GROUP BY escala ORDER BY cnt DESC
        """)
        escalas = c.fetchall()

        # Setores usados em colaboradores
        c.execute("""
            SELECT setor, COUNT(*) as cnt,
                   SUM(CASE WHEN auditavel = 1 THEN 1 ELSE 0 END) as auditaveis
            FROM colaboradores
            WHERE setor IS NOT NULL AND setor != ''
            GROUP BY setor ORDER BY cnt DESC
        """)
        setores_colab = c.fetchall()
        conn.close()

        lines = [self._header("Setores e Escalas")]

        lines.append("## Setores de Auditoria (definidos no sistema)\n")
        for s in sectors:
            lines.append(f"- **{s['id']}**: {s['label']}")
            if s["description"]:
                lines.append(f"  - {s['description']}")
        lines.append("")

        lines.append("## Setores dos Colaboradores (uso real)\n")
        for s in setores_colab:
            lines.append(f"- **{s['setor']}**: {s['cnt']} colaboradores ({s['auditaveis']} auditáveis)")
        lines.append("")

        lines.append("## Escalas\n")
        for e in escalas:
            lines.append(f"- **{e['escala']}**: {e['cnt']} colaboradores ({e['auditaveis']} auditáveis)")
        lines.append("")

        self._save("setores_e_escalas.md", "\n".join(lines))

    def _extract_criterios(self) -> None:
        lines = [self._header("Critérios de Auditoria")]

        # Load from YAML
        if self._scoring_rules_path.exists():
            with open(self._scoring_rules_path, "r", encoding="utf-8") as f:
                rules = yaml.safe_load(f)

            alerts = rules.get("alerts", [])
            lines.append(f"Total de alertas definidos: {len(alerts)}.\n\n")

            current_sector = None
            for alert in alerts:
                sector = alert.get("sector", "?")
                if sector != current_sector:
                    current_sector = sector
                    lines.append(f"## Setor: {sector}\n")

                lines.append(f"### {alert['label']} (`{alert['id']}`)\n")
                lines.append(f"- Referência POP: {alert.get('pop_ref', '?')}")
                if alert.get("context"):
                    lines.append(f"- Contexto: {alert['context']}")
                lines.append("")

                criteria = alert.get("criteria", [])
                for crit in criteria:
                    weight = crit.get("weight", 0)
                    label = crit.get("label", "?")
                    deflator = crit.get("deflator")
                    extra = f" (deflator: nota zerada)" if deflator else ""
                    lines.append(f"  - [{weight:.0%}] {label}{extra}")
                lines.append("")
        else:
            lines.append("Arquivo scoring_rules.yaml não encontrado.\n")

        self._save("criterios_auditoria.md", "\n".join(lines))

    @property
    def _scoring_rules_path(self) -> Path:
        return _SCORING_RULES_PATH

    def _extract_configuracoes(self) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT chave, valor, descricao FROM configuracoes ORDER BY chave")
        rows = c.fetchall()
        conn.close()

        lines = [self._header("Configurações do Sistema")]

        if rows:
            for r in rows:
                val = r["valor"] or "(vazio)"
                # Mask sensitive values
                if "senha" in (r["chave"] or "").lower() or "password" in (r["chave"] or "").lower():
                    val = "***"
                if "login_url" in (r["chave"] or "").lower() and val != "(vazio)":
                    val = val[:50] + "..." if len(val) > 50 else val
                lines.append(f"- **{r['chave']}** = `{val}`")
                if r["descricao"]:
                    lines.append(f"  - {r['descricao']}")
            lines.append("")
        else:
            lines.append("Nenhuma configuração encontrada.\n")

        self._save("configuracoes.md", "\n".join(lines))

    def _extract_usuarios(self) -> None:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT username, role, supervisor_name FROM users ORDER BY role, username")
        rows = c.fetchall()
        conn.close()

        lines = [self._header("Usuários do Sistema")]
        lines.append(f"Total de usuários: {len(rows)}.\n\n")

        by_role: dict[str, list] = {}
        for r in rows:
            by_role.setdefault(r["role"] or "sem_role", []).append(r)

        for role in sorted(by_role.keys()):
            users = by_role[role]
            lines.append(f"## Role: {role} ({len(users)} usuários)\n")
            for u in users:
                sup = f" — supervisor: {u['supervisor_name']}" if u["supervisor_name"] else ""
                lines.append(f"- **{u['username']}**{sup}")
            lines.append("")

        self._save("usuarios.md", "\n".join(lines))

    def _extract_schema(self) -> None:
        conn = self._conn()
        c = conn.cursor()

        # List tables
        c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
        tables = [row[0] for row in c.fetchall()]

        # List views
        c.execute(
            "SELECT table_name, view_definition FROM information_schema.views "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        views = c.fetchall()

        lines = [self._header("Estrutura do Banco de Dados")]
        lines.append(f"Total: {len(tables)} tabelas, {len(views)} views.\n\n")

        lines.append("## Tabelas\n")
        for tname in tables:
            lines.append(f"### {tname}\n")
            c.execute(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
                (tname,),
            )
            cols = c.fetchall()
            lines.append("| Coluna | Tipo | Nullable | Default |")
            lines.append("|--------|------|----------|---------|")
            for col in cols:
                lines.append(f"| {col[0]} | {col[1]} | {col[2]} | {col[3] or ''} |")
            lines.append("")

        if views:
            lines.append("## Views\n")
            for v in views:
                lines.append(f"### {v[0]}\n")
                lines.append("```sql")
                lines.append(v[1] or "-- sem definição")
                lines.append("```\n")

        conn.close()
        self._save("estrutura_banco.md", "\n".join(lines))

    def _extract_estatisticas(self) -> None:
        conn = self._conn()
        c = conn.cursor()

        stats = {}

        # Collaborators
        c.execute("SELECT COUNT(*) FROM colaboradores")
        stats["total_colaboradores"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM colaboradores WHERE auditavel = 1")
        stats["auditaveis"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM colaboradores WHERE auditavel = 0")
        stats["nao_auditaveis"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM colaboradores WHERE supervisor IS NOT NULL AND supervisor != ''")
        stats["com_supervisor"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM colaboradores WHERE supervisor IS NULL OR supervisor = ''")
        stats["sem_supervisor"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM colaboradores WHERE auditavel = 1 AND (supervisor IS NULL OR supervisor = '')")
        stats["auditaveis_sem_supervisor"] = c.fetchone()[0]

        # Audits
        c.execute("SELECT COUNT(*) FROM audits")
        stats["total_auditorias"] = c.fetchone()[0]

        # Users
        c.execute("SELECT COUNT(*) FROM users")
        stats["total_usuarios"] = c.fetchone()[0]

        # Sectors and alerts
        c.execute("SELECT COUNT(*) FROM audit_sectors")
        stats["total_setores_auditoria"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM audit_alerts")
        stats["total_alertas"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM audit_criteria")
        stats["total_criterios"] = c.fetchone()[0]

        # Ligações
        c.execute("SELECT COUNT(*) FROM ligacoes_auditadas")
        stats["total_ligacoes_auditadas"] = c.fetchone()[0]

        # Configs
        c.execute("SELECT COUNT(*) FROM configuracoes")
        stats["total_configuracoes"] = c.fetchone()[0]

        # Tables with row counts
        table_counts = {}
        c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
        for row in c.fetchall():
            tname = row[0]
            try:
                c.execute(f'SELECT COUNT(*) FROM "{tname}"')
                table_counts[tname] = c.fetchone()[0]
            except Exception:
                table_counts[tname] = "erro"

        conn.close()

        lines = [self._header("Estatísticas do Banco de Dados")]

        lines.append("## Resumo Geral\n")
        lines.append(f"- Total de colaboradores: {stats['total_colaboradores']}")
        lines.append(f"  - Auditáveis: {stats['auditaveis']}")
        lines.append(f"  - Não auditáveis: {stats['nao_auditaveis']}")
        lines.append(f"  - Com supervisor: {stats['com_supervisor']}")
        lines.append(f"  - Sem supervisor: {stats['sem_supervisor']}")
        lines.append(f"  - Auditáveis sem supervisor: {stats['auditaveis_sem_supervisor']}")
        lines.append(f"- Total de auditorias realizadas: {stats['total_auditorias']}")
        lines.append(f"- Total de usuários: {stats['total_usuarios']}")
        lines.append(f"- Setores de auditoria: {stats['total_setores_auditoria']}")
        lines.append(f"- Alertas definidos: {stats['total_alertas']}")
        lines.append(f"- Critérios de avaliação: {stats['total_criterios']}")
        lines.append(f"- Ligações catalogadas: {stats['total_ligacoes_auditadas']}")
        lines.append(f"- Configurações: {stats['total_configuracoes']}")
        lines.append("")

        # Completude
        if stats["total_colaboradores"] > 0:
            pct_sup = 100 * stats["com_supervisor"] / stats["total_colaboradores"]
            pct_aud = 100 * stats["auditaveis"] / stats["total_colaboradores"]
            lines.append("## Indicadores de Completude\n")
            lines.append(f"- Colaboradores com supervisor: {pct_sup:.0f}%")
            lines.append(f"- Colaboradores auditáveis: {pct_aud:.0f}%")

            if stats["auditaveis"] > 0:
                pct_aud_sup = 100 * (stats["auditaveis"] - stats["auditaveis_sem_supervisor"]) / stats["auditaveis"]
                lines.append(f"- Auditáveis com supervisor: {pct_aud_sup:.0f}%")
            lines.append("")

        lines.append("## Contagem por Tabela\n")
        for table, count in sorted(table_counts.items()):
            lines.append(f"- `{table}`: {count} registros")
        lines.append("")

        self._save("estatisticas.md", "\n".join(lines))

    def _extract_regras_negocio(self) -> None:
        lines = [self._header("Regras de Negócio")]
        lines.append(
            "Regras extraídas dos documentos oficiais em `docs/references/`, "
            "`instrucoes/` e POPs curados em "
            "`rag/sources/procedimentos_operacionais/`.\n\n"
        )

        # Manual Técnico Qualidade
        manual_path = _INSTRUCOES_DIR / "Manual tecnico Qualidade.md"
        if manual_path.exists():
            content = manual_path.read_text(encoding="utf-8")
            lines.append("## Manual Técnico de Qualidade\n")
            lines.append(content)
            lines.append("\n---\n")

        # Procedimento de Automação
        proc_path = _INSTRUCOES_DIR / "PROCEDIMENTO_AUTOMATIZACAO.md"
        if proc_path.exists():
            content = proc_path.read_text(encoding="utf-8")
            lines.append("## Procedimento de Automação\n")
            lines.append(content)
            lines.append("\n---\n")

        # Dicionário Logístico
        dict_path = _OPERACIONAL_REFERENCES_DIR / "DICIONARIO_LOGISTICO.md"
        if dict_path.exists():
            content = dict_path.read_text(encoding="utf-8")
            lines.append("## Dicionário Logístico\n")
            lines.append(content)
            lines.append("\n---\n")

        # Instruções de padrão de auditoria
        padrao_path = _AUDITORIA_REFERENCES_DIR / "criterios-auditoria-opentech.md"
        if padrao_path.exists():
            content = padrao_path.read_text(encoding="utf-8")
            lines.append("## Instruções de Padrão de Auditoria\n")
            lines.append(content)
            lines.append("\n---\n")

        # POPs oficiais (rag/sources/procedimentos_operacionais/)
        pops_dir = _RAG_SOURCES_DIR / "procedimentos_operacionais"
        if pops_dir.exists():
            lines.append("## Procedimentos Operacionais Padrão (POPs)\n")
            lines.append(
                "Fontes oficiais curadas em `rag/sources/procedimentos_operacionais/`. "
                "Cada arquivo cobre um setor ou conjunto de setores com critérios "
                "detalhados por alerta/fluxo.\n\n"
            )
            for pop_path in sorted(pops_dir.glob("*.md")):
                if pop_path.name.startswith("_"):
                    continue  # ignora _INDEX.md
                content = pop_path.read_text(encoding="utf-8")
                lines.append(f"### Fonte: `{pop_path.name}`\n")
                lines.append(content)
                lines.append("\n---\n")

        self._save("regras_negocio.md", "\n".join(lines))

    def _write_index(self) -> None:
        lines = [self._header("Índice de Documentos RAG")]
        lines.append(
            "Este índice lista todos os documentos gerados pelo DB Knowledge Agent "
            "para uso em RAG (Retrieval-Augmented Generation).\n\n"
        )

        descriptions = {
            "colaboradores.md": "Lista completa de colaboradores com supervisor, setor, escala e status.",
            "supervisores.md": "Mapeamento de cada supervisor para sua equipe, setores e escalas.",
            "setores_e_escalas.md": "Setores de auditoria, escalas operacionais e contagens.",
            "criterios_auditoria.md": "Critérios de avaliação por tipo de alerta e setor (do POP oficial).",
            "configuracoes.md": "Configurações atuais do sistema (RPA, login, IA).",
            "usuarios.md": "Usuários cadastrados com seus roles e supervisores.",
            "estrutura_banco.md": "Schema DDL de todas as tabelas e views.",
            "estatisticas.md": "Métricas de completude e contagens do banco.",
            "regras_negocio.md": "Regras de negócio extraídas dos manuais oficiais.",
        }

        lines.append("## Documentos\n")
        for fname in self._generated_files:
            if fname == "_INDEX.md":
                continue
            desc = descriptions.get(fname, "")
            lines.append(f"- **{fname}**: {desc}")
        lines.append("")

        self._save("_INDEX.md", "\n".join(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    agent = DBKnowledgeAgent()
    files = agent.run()
    print(f"\n✓ {len(files)} documentos gerados em: {agent.output_dir}")
    for f in files:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
