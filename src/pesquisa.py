from __future__ import annotations

from pathlib import Path

from src.utils import atualizar_status


def gerar_pesquisa(pasta_projeto: Path) -> None:
    tema = _tema(pasta_projeto)
    pesquisa_dir = pasta_projeto / "pesquisa"
    pesquisa_dir.mkdir(parents=True, exist_ok=True)

    (pesquisa_dir / "briefing.md").write_text(_briefing(tema), encoding="utf-8")
    (pesquisa_dir / "fontes.md").write_text(_fontes(tema), encoding="utf-8")
    (pesquisa_dir / "pendencias.md").write_text(_pendencias(tema), encoding="utf-8")
    atualizar_status(pasta_projeto, pesquisa="concluido")
    print("Pesquisa gerada")


def _tema(pasta_projeto: Path) -> str:
    tema_path = pasta_projeto / "tema.txt"
    if tema_path.exists():
        return tema_path.read_text(encoding="utf-8").strip()
    return pasta_projeto.name.replace("_", " ").title()


def _briefing(tema: str) -> str:
    return "\n".join(
        [
            f"# Briefing factual: {tema}",
            "",
            "## Resumo",
            f"O tema `{tema}` sera tratado como uma curiosidade curta em tom documental.",
            "A abordagem deve separar reputacao, contexto cultural, mito popular e realidade pratica.",
            "",
            "## Pontos principais",
            "- Apresentar um gancho forte sem prometer uma verdade absoluta.",
            "- Explicar por que o assunto ficou conhecido na cultura popular.",
            "- Comparar mito e realidade em linguagem simples.",
            "- Evitar qualquer instrucao operacional, tecnica ou perigosa.",
            "- Fechar com uma ideia memoravel e segura para publicacao.",
            "",
            "## Contexto historico e cultural",
            "Use o tema como ponto de partida para falar de fama, representacao publica, cinema,",
            "memoria coletiva e exageros comuns em conversas informais.",
            "",
            "## Alertas editoriais",
            "- Revisar datas, nomes e dados tecnicos antes de publicar.",
            "- Nao ensinar uso, modificacao, obtencao ou melhora de desempenho de armas.",
            "- Preferir linguagem cultural, historica e educativa.",
            "",
            "## Perguntas factuais",
            "- Quais nomes, datas ou obras precisam ser confirmados?",
            "- Existe diferenca entre reputacao cultural e dado tecnico verificavel?",
            "- Alguma frase pode soar instrucional ou incentivar pratica perigosa?",
            "- As imagens e videos usados tem licenca ou autorizacao clara?",
        ]
    ) + "\n"


def _fontes(tema: str) -> str:
    return "\n".join(
        [
            f"# Fontes sugeridas para revisar: {tema}",
            "",
            "Nenhuma busca automatica foi feita nesta etapa.",
            "",
            "Sugestoes para checagem manual:",
            "- Wikipedia e Wikimedia Commons, quando o assunto tiver verbetes e midias livres.",
            "- Enciclopedias, livros ou artigos historicos.",
            "- Sites oficiais de museus, fabricantes, arquivos ou instituicoes reconhecidas.",
            "- Materiais com licenca clara para imagens ou videos.",
            "",
            "Registre aqui os links consultados antes da postagem final.",
        ]
    ) + "\n"


def _pendencias(tema: str) -> str:
    return "\n".join(
        [
            f"# Pendencias de checagem: {tema}",
            "",
            "- Verificar datas.",
            "- Verificar dados tecnicos.",
            "- Verificar nomes.",
            "- Verificar afirmacoes sensiveis.",
            "- Revisar se o roteiro nao ensina pratica perigosa.",
            "- Revisar direitos das imagens/videos usados.",
            "- Confirmar se comparacoes sao culturais, nao instrucionais.",
            "- Revisar o roteiro final antes de publicar.",
        ]
    ) + "\n"
