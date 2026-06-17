from __future__ import annotations

from pathlib import Path

from src.utils import carregar_json_arquivo, atualizar_status


def ler_srt(caminho_srt: Path) -> list[dict]:
    if not caminho_srt.exists() or caminho_srt.stat().st_size == 0:
        return []
    conteudo = caminho_srt.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    blocos = []
    for bloco in conteudo.split("\n\n"):
        linhas = [linha.strip() for linha in bloco.splitlines() if linha.strip()]
        if len(linhas) < 3:
            continue
        tempo_idx = 1 if linhas[0].isdigit() else 0
        if tempo_idx >= len(linhas) or "-->" not in linhas[tempo_idx]:
            continue
        inicio_raw, fim_raw = [parte.strip() for parte in linhas[tempo_idx].split("-->", 1)]
        inicio = _parse_srt_time(inicio_raw)
        fim = _parse_srt_time(fim_raw)
        texto = " ".join(linhas[tempo_idx + 1 :]).strip()
        if inicio is not None and fim is not None and fim > inicio and texto:
            blocos.append({"inicio": inicio, "fim": fim, "texto": texto})
    return blocos


def legenda_ativa_no_tempo(blocos_srt: list[dict], tempo: float) -> str:
    for bloco in blocos_srt:
        if float(bloco["inicio"]) <= tempo < float(bloco["fim"]):
            return str(bloco["texto"])
    return ""


def duracao_srt(blocos_srt: list[dict]) -> float | None:
    if not blocos_srt:
        return None
    return max(float(bloco["fim"]) for bloco in blocos_srt)


def gerar_legendas(pasta_projeto: Path) -> Path:
    legenda = pasta_projeto / "legendas" / "legenda.srt"
    if _legenda_edge_tts_existe(pasta_projeto, legenda):
        _copiar_para_pacote(pasta_projeto, legenda)
        atualizar_status(pasta_projeto, legendas="sincronizada_edge_tts")
        print("Legenda sincronizada preservada")
        return legenda
    if _fonte_edge_tts(pasta_projeto):
        raise RuntimeError(
            "ERRO: fonte_legenda.txt indica edge-tts, mas legendas/legenda.srt nao foi encontrada. "
            "Rode: python main.py narracao --projeto NOME_DO_PROJETO"
        )

    cenas = carregar_json_arquivo(pasta_projeto / "cenas.json", default=[])
    linhas = []
    for idx, cena in enumerate(cenas, start=1):
        inicio = float(cena.get("inicio_estimado", 0))
        fim = inicio + float(cena.get("duracao", 5))
        texto = cena.get("legenda_curta") or cena.get("narracao", "")
        linhas.extend(
            [
                str(idx),
                f"{_srt_time(inicio)} --> {_srt_time(fim)}",
                _formatar_bloco_legenda(texto),
                "",
            ]
        )

    legenda.parent.mkdir(parents=True, exist_ok=True)
    legenda.write_text("\n".join(linhas), encoding="utf-8")
    (pasta_projeto / "legendas" / "fonte_legenda.txt").write_text("estimada\n", encoding="utf-8")

    _copiar_para_pacote(pasta_projeto, legenda)
    atualizar_status(pasta_projeto, legendas="concluido")
    print("Legenda gerada")
    return legenda


def _legenda_edge_tts_existe(pasta_projeto: Path, legenda: Path) -> bool:
    if not legenda.exists() or legenda.stat().st_size == 0:
        return False
    fonte = pasta_projeto / "legendas" / "fonte_legenda.txt"
    if not fonte.exists() or "edge-tts" not in fonte.read_text(encoding="utf-8", errors="replace"):
        return False
    texto = legenda.read_text(encoding="utf-8", errors="replace")
    return "-->" in texto


def _fonte_edge_tts(pasta_projeto: Path) -> bool:
    fonte = pasta_projeto / "legendas" / "fonte_legenda.txt"
    return fonte.exists() and "edge-tts" in fonte.read_text(encoding="utf-8", errors="replace")


def _copiar_para_pacote(pasta_projeto: Path, legenda: Path) -> None:
    destino = pasta_projeto / "pacote_postagem" / "legenda.srt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(legenda.read_text(encoding="utf-8"), encoding="utf-8")


def _srt_time(segundos: float) -> str:
    total_ms = max(0, int(round(segundos * 1000)))
    horas = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutos = total_ms // 60_000
    total_ms %= 60_000
    seg = total_ms // 1000
    ms = total_ms % 1000
    return f"{horas:02}:{minutos:02}:{seg:02},{ms:03}"


def _parse_srt_time(valor: str) -> float | None:
    try:
        horas, minutos, resto = valor.replace(".", ",").split(":")
        segundos, ms = resto.split(",", 1)
        return int(horas) * 3600 + int(minutos) * 60 + int(segundos) + int(ms[:3].ljust(3, "0")) / 1000
    except (ValueError, IndexError):
        return None


def _formatar_bloco_legenda(texto: str) -> str:
    palavras = " ".join((texto or "").split()).split()
    if not palavras:
        return ""
    linhas = []
    atual = ""
    for palavra in palavras:
        tentativa = f"{atual} {palavra}".strip()
        if len(tentativa) <= 42:
            atual = tentativa
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
        if len(linhas) == 2:
            break
    if atual and len(linhas) < 2:
        linhas.append(atual)
    return "\n".join(linhas[:2])
