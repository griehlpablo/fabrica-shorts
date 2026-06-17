from __future__ import annotations

from pathlib import Path

from src.utils import carregar_json_arquivo, atualizar_status


def gerar_legendas(pasta_projeto: Path) -> Path:
    cenas = carregar_json_arquivo(pasta_projeto / "cenas.json", default=[])
    linhas = []
    for idx, cena in enumerate(cenas, start=1):
        inicio = int(cena.get("inicio_estimado", 0))
        fim = inicio + int(cena.get("duracao", 5))
        linhas.extend(
            [
                str(idx),
                f"{_srt_time(inicio)} --> {_srt_time(fim)}",
                cena.get("narracao", ""),
                "",
            ]
        )

    legenda = pasta_projeto / "legendas" / "legenda.srt"
    legenda.parent.mkdir(parents=True, exist_ok=True)
    legenda.write_text("\n".join(linhas), encoding="utf-8")

    destino = pasta_projeto / "pacote_postagem" / "legenda.srt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(legenda.read_text(encoding="utf-8"), encoding="utf-8")
    atualizar_status(pasta_projeto, montagem="legenda_gerada")
    return legenda


def _srt_time(segundos: int) -> str:
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    seg = segundos % 60
    return f"{horas:02}:{minutos:02}:{seg:02},000"
