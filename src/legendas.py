from __future__ import annotations

import re
from pathlib import Path

from src.utils import atualizar_status, carregar_json_arquivo, normalizar_texto_portugues


FONTES_SINCRONIZADAS = {"stable-ts", "edge-tts"}


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
        texto = normalizar_texto_portugues(" ".join(linhas[tempo_idx + 1 :]))
        if inicio is not None and fim is not None and fim > inicio and texto:
            blocos.append({"inicio": inicio, "fim": fim, "texto": texto})
    return blocos


def salvar_srt(blocos: list[dict], caminho_srt: Path) -> Path:
    caminho_srt.parent.mkdir(parents=True, exist_ok=True)
    linhas = []
    for idx, bloco in enumerate(blocos, start=1):
        linhas.extend(
            [
                str(idx),
                f"{_srt_time(float(bloco['inicio']))} --> {_srt_time(float(bloco['fim']))}",
                _formatar_bloco_legenda(str(bloco.get("texto", ""))),
                "",
            ]
        )
    caminho_srt.write_text("\n".join(linhas), encoding="utf-8")
    return caminho_srt


def legenda_ativa_no_tempo(blocos_srt: list[dict], tempo: float) -> str:
    for bloco in blocos_srt:
        if float(bloco["inicio"]) <= tempo < float(bloco["fim"]):
            return str(bloco["texto"])
    return ""


def duracao_srt(blocos_srt: list[dict]) -> float | None:
    if not blocos_srt:
        return None
    return max(float(bloco["fim"]) for bloco in blocos_srt)


def fonte_legenda(pasta_projeto: Path) -> str:
    fonte = pasta_projeto / "legendas" / "fonte_legenda.txt"
    if not fonte.exists():
        return ""
    return fonte.read_text(encoding="utf-8", errors="replace").strip()


def legenda_sincronizada(pasta_projeto: Path) -> bool:
    return fonte_legenda(pasta_projeto) in FONTES_SINCRONIZADAS


def gerar_legendas(pasta_projeto: Path) -> Path:
    legenda = pasta_projeto / "legendas" / "legenda.srt"
    fonte = fonte_legenda(pasta_projeto)
    if fonte in FONTES_SINCRONIZADAS:
        if _legenda_valida(legenda):
            gerar_ass_de_srt(pasta_projeto, legenda)
            _copiar_para_pacote(pasta_projeto, legenda)
            atualizar_status(pasta_projeto, legendas=f"sincronizada_{fonte}")
            print(f"Legenda sincronizada preservada ({fonte})")
            return legenda
        raise RuntimeError(
            f"ERRO: fonte_legenda.txt indica {fonte}, mas legendas/legenda.srt nao foi encontrada. "
            f"Rode: python main.py alinhar --projeto {pasta_projeto.name}"
        )

    edge_raw = pasta_projeto / "legendas" / "edge_tts_raw.srt"
    if _legenda_valida(edge_raw):
        blocos = dividir_blocos_longos(ler_srt(edge_raw))
        salvar_srt(blocos, legenda)
        (pasta_projeto / "legendas" / "fonte_legenda.txt").write_text("edge-tts\n", encoding="utf-8")
        _copiar_para_pacote(pasta_projeto, legenda)
        gerar_ass_de_srt(pasta_projeto, legenda)
        atualizar_status(pasta_projeto, legendas="sincronizada_edge_tts")
        print("Legenda edge-tts usada como fallback")
        return legenda

    cenas = carregar_json_arquivo(pasta_projeto / "cenas.json", default=[])
    blocos = []
    for cena in cenas:
        inicio = float(cena.get("inicio_estimado", 0))
        fim = inicio + float(cena.get("duracao", 5))
        texto = cena.get("narracao", "")
        blocos.append({"inicio": inicio, "fim": fim, "texto": texto})
    blocos = dividir_blocos_longos(blocos)
    salvar_srt(blocos, legenda)
    (pasta_projeto / "legendas" / "fonte_legenda.txt").write_text("estimada\n", encoding="utf-8")
    _copiar_para_pacote(pasta_projeto, legenda)
    gerar_ass_de_srt(pasta_projeto, legenda)
    atualizar_status(pasta_projeto, legendas="concluido")
    print("Legenda estimada gerada")
    return legenda


def dividir_blocos_longos(blocos: list[dict], max_palavras: int = 10, max_chars: int = 52) -> list[dict]:
    resultado = []
    for bloco in blocos:
        texto = normalizar_texto_portugues(str(bloco.get("texto", "")))
        partes = _dividir_texto_legenda(texto, max_palavras=max_palavras, max_chars=max_chars)
        if len(partes) <= 1:
            if texto:
                resultado.append({"inicio": float(bloco["inicio"]), "fim": float(bloco["fim"]), "texto": texto})
            continue
        inicio = float(bloco["inicio"])
        fim = float(bloco["fim"])
        duracao = max(0.05, fim - inicio)
        pesos = [max(1, len(parte.split())) for parte in partes]
        soma = sum(pesos)
        cursor = inicio
        for idx, parte in enumerate(partes):
            if idx == len(partes) - 1:
                sub_fim = fim
            else:
                sub_fim = cursor + duracao * pesos[idx] / soma
            resultado.append({"inicio": cursor, "fim": sub_fim, "texto": parte})
            cursor = sub_fim
    return resultado


def gerar_ass_de_srt(pasta_projeto: Path, srt_path: Path | None = None) -> Path | None:
    srt_path = srt_path or pasta_projeto / "legendas" / "legenda.srt"
    blocos = dividir_blocos_longos(ler_srt(srt_path), max_palavras=9, max_chars=48)
    if not blocos:
        return None
    ass_path = pasta_projeto / "legendas" / "legenda.ass"
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    linhas = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Shorts,Arial,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,1,0,0,0,100,100,0,0,1,4,2,2,90,90,360,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for bloco in blocos:
        texto = _ass_texto(_formatar_bloco_legenda(str(bloco["texto"]), max_chars=30, max_linhas=2))
        linhas.append(
            f"Dialogue: 0,{_ass_time(float(bloco['inicio']))},{_ass_time(float(bloco['fim']))},Shorts,,0,0,0,,{texto}"
        )
    ass_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return ass_path


def _legenda_valida(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0 and "-->" in path.read_text(encoding="utf-8", errors="replace")


def _dividir_texto_legenda(texto: str, max_palavras: int, max_chars: int) -> list[str]:
    texto = normalizar_texto_portugues(texto)
    if not texto:
        return []
    frases = [p.strip() for p in re.split(r"(?<=[.!?])\s+", texto) if p.strip()]
    partes = []
    for frase in frases or [texto]:
        palavras = frase.split()
        atual = []
        for palavra in palavras:
            tentativa = " ".join([*atual, palavra])
            if atual and (len(atual) >= max_palavras or len(tentativa) > max_chars):
                partes.append(" ".join(atual))
                atual = [palavra]
            else:
                atual.append(palavra)
        if atual:
            partes.append(" ".join(atual))
    return partes


def _formatar_bloco_legenda(texto: str, max_chars: int = 42, max_linhas: int = 2) -> str:
    partes = _dividir_texto_legenda(texto, max_palavras=8, max_chars=max_chars)
    if len(partes) <= max_linhas:
        return "\n".join(partes)
    return "\n".join(partes[:max_linhas])


def _copiar_para_pacote(pasta_projeto: Path, legenda: Path) -> None:
    destino = pasta_projeto / "pacote_postagem" / "legenda.srt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(legenda.read_text(encoding="utf-8"), encoding="utf-8")
    ass = pasta_projeto / "legendas" / "legenda.ass"
    if ass.exists():
        (pasta_projeto / "pacote_postagem" / "legenda.ass").write_text(ass.read_text(encoding="utf-8"), encoding="utf-8")


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


def _ass_time(segundos: float) -> str:
    total_cs = max(0, int(round(segundos * 100)))
    horas = total_cs // 360000
    total_cs %= 360000
    minutos = total_cs // 6000
    total_cs %= 6000
    seg = total_cs // 100
    cs = total_cs % 100
    return f"{horas}:{minutos:02}:{seg:02}.{cs:02}"


def _ass_texto(texto: str) -> str:
    return (
        texto.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r\n", "\n")
        .replace("\n", r"\N")
    )
