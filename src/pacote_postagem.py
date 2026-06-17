from __future__ import annotations

from pathlib import Path

from src.utils import atualizar_status


HASHTAGS_FIXAS = ["#shorts", "#curiosidades", "#documentario", "#fatos"]


def gerar_pacote(pasta_projeto: Path) -> None:
    pacote = pasta_projeto / "pacote_postagem"
    pacote.mkdir(parents=True, exist_ok=True)
    tema = (pasta_projeto / "tema.txt").read_text(encoding="utf-8").strip()

    (pacote / "titulo.txt").write_text(f"{tema}\n", encoding="utf-8")
    (pacote / "descricao.txt").write_text(_descricao(tema), encoding="utf-8")
    (pacote / "hashtags.txt").write_text("\n".join(_hashtags(tema)) + "\n", encoding="utf-8")
    (pacote / "checklist_publicacao.txt").write_text(
        "\n".join(
            [
                "[ ] Revisar fatos.",
                "[ ] Revisar direitos das midias.",
                "[ ] Confirmar que o conteudo nao ensina pratica perigosa.",
                "[ ] Conferir audio.",
                "[ ] Conferir legenda.",
                "[ ] Conferir se o video esta em 1080x1920.",
                "[ ] Postar manualmente nas plataformas.",
                "[ ] Evitar marca d'agua.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    legenda = pasta_projeto / "legendas" / "legenda.srt"
    if legenda.exists():
        (pacote / "legenda.srt").write_text(legenda.read_text(encoding="utf-8"), encoding="utf-8")

    atualizar_status(pasta_projeto, status="pacote_pronto", pacote="concluido")
    print("Pacote de postagem gerado")


def _descricao(tema: str) -> str:
    return f"Curiosidade em formato documental sobre {tema}, separando mito, contexto e realidade.\n"


def _hashtags(tema: str) -> list[str]:
    extras = []
    for parte in tema.lower().replace(".", " ").split():
        tag = "".join(ch for ch in parte if ch.isalnum())
        if len(tag) >= 4:
            extras.append("#" + tag)
    resultado = []
    for tag in extras + HASHTAGS_FIXAS:
        if tag not in resultado:
            resultado.append(tag)
    return resultado[:10]
