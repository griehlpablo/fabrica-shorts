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
                "[ ] Conferir fontes_midias.json.",
                "[ ] Confirmar se midias locais sao proprias, autorizadas ou licenciadas.",
                "[ ] Conferir se midias externas tem URL, licenca e autor.",
                "[ ] Revisar se midia externa tem licenca registrada.",
                "[ ] Revisar se nao ha conteudo sensivel problematico.",
                "[ ] Revisar se o roteiro nao ensina uso de arma.",
                "[ ] Revisar se o video nao mostra gore ou violencia.",
                "[ ] Revisar se o video ficou denso o suficiente.",
                "[ ] Revisar se nao ha elementos de template no topo, barra ou contador.",
                "[ ] Revisar direitos das midias locais.",
                "[ ] Conferir se o video tem audio.",
                "[ ] Conferir legenda.",
                "[ ] Conferir acentos.",
                "[ ] Conferir se nao ha reticencias artificiais.",
                "[ ] Conferir se o video esta em 1080x1920.",
                "[ ] Conferir conteudo sensivel.",
                "[ ] Postar manualmente nas plataformas.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    legenda = pasta_projeto / "legendas" / "legenda.srt"
    if legenda.exists():
        (pacote / "legenda.srt").write_text(legenda.read_text(encoding="utf-8"), encoding="utf-8")
    legenda_ass = pasta_projeto / "legendas" / "legenda.ass"
    if legenda_ass.exists():
        (pacote / "legenda.ass").write_text(legenda_ass.read_text(encoding="utf-8"), encoding="utf-8")
    for nome in ["fontes_midias.json", "plano_visual.json", "shotlist.md", "plano_midias.json"]:
        origem = pasta_projeto / nome
        if origem.exists():
            (pacote / nome).write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")

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
