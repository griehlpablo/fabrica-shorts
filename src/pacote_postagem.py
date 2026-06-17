from __future__ import annotations

from pathlib import Path

from src.utils import atualizar_status


HASHTAGS = ["#shorts", "#curiosidades", "#historia", "#documentario", "#fatos"]


def gerar_pacote(pasta_projeto: Path) -> None:
    pacote = pasta_projeto / "pacote_postagem"
    pacote.mkdir(parents=True, exist_ok=True)
    tema = (pasta_projeto / "tema.txt").read_text(encoding="utf-8").strip()

    (pacote / "titulo.txt").write_text(f"{tema}\n", encoding="utf-8")
    (pacote / "descricao.txt").write_text(
        f"Um video curto de curiosidade sobre {tema}, separando mito, contexto e realidade.\n",
        encoding="utf-8",
    )
    (pacote / "hashtags.txt").write_text("\n".join(HASHTAGS) + "\n", encoding="utf-8")
    (pacote / "checklist_publicacao.txt").write_text(
        "\n".join(
            [
                "[ ] Revisar direitos das midias.",
                "[ ] Conferir se nao ha musica protegida.",
                "[ ] Conferir se trechos de filme, serie, transmissao ou podcast foram autorizados.",
                "[ ] Conferir se o video esta em 1080x1920.",
                "[ ] Conferir se legenda e texto estao corretos.",
                "[ ] Postar manualmente em YouTube Shorts, TikTok, Kwai, Instagram Reels e Facebook Reels.",
                "[ ] Evitar marca d'agua de uma plataforma ao repostar em outra.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    legenda = pasta_projeto / "legendas" / "legenda.srt"
    if legenda.exists():
        (pacote / "legenda.srt").write_text(legenda.read_text(encoding="utf-8"), encoding="utf-8")

    atualizar_status(pasta_projeto, status="pacote_pronto", pacote="concluido")
