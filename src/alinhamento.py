from __future__ import annotations

import traceback
from pathlib import Path

from src.legendas import dividir_blocos_longos, gerar_ass_de_srt, gerar_legendas, ler_srt, salvar_srt
from src.utils import atualizar_status, normalizar_texto_portugues


def alinhar_legenda(base_dir: Path, pasta_projeto: Path, modelo: str = "base") -> Path:
    audio = _audio_narracao(pasta_projeto)
    if not audio:
        raise RuntimeError(
            "ERRO: audio/narracao.mp3 nao foi encontrado. Rode:\n"
            f"python main.py narracao --projeto {pasta_projeto.name}"
        )

    roteiro_path = pasta_projeto / "roteiro" / "roteiro_narrado.txt"
    if not roteiro_path.exists():
        roteiro_path = pasta_projeto / "roteiro.txt"
    texto = normalizar_texto_portugues(roteiro_path.read_text(encoding="utf-8"))
    if not texto:
        raise RuntimeError("ERRO: roteiro narrado vazio; nao foi possivel alinhar legenda.")

    legenda_dir = pasta_projeto / "legendas"
    legenda_dir.mkdir(parents=True, exist_ok=True)
    srt_final = legenda_dir / "legenda.srt"
    log_path = pasta_projeto / "logs" / "alinhamento_erro.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        blocos = _alinhar_com_stable_ts(audio, texto, modelo=modelo, cache_dir=base_dir / ".cache" / "whisper")
        blocos = dividir_blocos_longos(blocos)
        salvar_srt(blocos, srt_final)
        (legenda_dir / "fonte_legenda.txt").write_text("stable-ts\n", encoding="utf-8")
        ass = gerar_ass_de_srt(pasta_projeto, srt_final)
        _copiar_para_pacote(pasta_projeto, srt_final, ass)
        atualizar_status(pasta_projeto, legendas="sincronizada_stable_ts")
        print(f"Legenda alinhada com stable-ts: {srt_final}")
        print(f"Blocos SRT gerados: {len(blocos)}")
        if ass:
            print(f"Legenda ASS gerada em: {ass}")
        return srt_final
    except Exception as exc:
        log_path.write_text(
            "Falha ao alinhar com stable-ts.\n\n"
            f"Erro: {exc}\n\n"
            f"Traceback:\n{traceback.format_exc()}",
            encoding="utf-8",
        )
        print(f"stable-ts falhou; usando fallback de legenda. Log: {log_path}")
        return _fallback_legenda(pasta_projeto)


def _alinhar_com_stable_ts(audio: Path, texto: str, modelo: str, cache_dir: Path) -> list[dict]:
    import stable_whisper

    cache_dir.mkdir(parents=True, exist_ok=True)
    model = stable_whisper.load_model(modelo, download_root=str(cache_dir))
    resultado = model.align(str(audio), texto, language="pt")
    blocos = _blocos_do_resultado(resultado)
    if not blocos:
        raise RuntimeError("stable-ts nao retornou segmentos de alinhamento.")
    return blocos


def _blocos_do_resultado(resultado) -> list[dict]:
    segmentos = getattr(resultado, "segments", None) or []
    blocos = []
    for segmento in segmentos:
        inicio = getattr(segmento, "start", None)
        fim = getattr(segmento, "end", None)
        texto = getattr(segmento, "text", None)
        if isinstance(segmento, dict):
            inicio = segmento.get("start", inicio)
            fim = segmento.get("end", fim)
            texto = segmento.get("text", texto)
        if inicio is None or fim is None:
            continue
        texto = normalizar_texto_portugues(str(texto or ""))
        if texto and float(fim) > float(inicio):
            blocos.append({"inicio": float(inicio), "fim": float(fim), "texto": texto})
    return blocos


def _fallback_legenda(pasta_projeto: Path) -> Path:
    legenda_dir = pasta_projeto / "legendas"
    srt_final = legenda_dir / "legenda.srt"
    edge_raw = legenda_dir / "edge_tts_raw.srt"
    if edge_raw.exists() and edge_raw.stat().st_size > 0:
        blocos = dividir_blocos_longos(ler_srt(edge_raw))
        salvar_srt(blocos, srt_final)
        (legenda_dir / "fonte_legenda.txt").write_text("edge-tts\n", encoding="utf-8")
        ass = gerar_ass_de_srt(pasta_projeto, srt_final)
        _copiar_para_pacote(pasta_projeto, srt_final, ass)
        atualizar_status(pasta_projeto, legendas="sincronizada_edge_tts")
        print(f"Fallback edge-tts usado: {srt_final}")
        print(f"Blocos SRT gerados: {len(blocos)}")
        return srt_final
    return gerar_legendas(pasta_projeto)


def _copiar_para_pacote(pasta_projeto: Path, srt: Path, ass: Path | None) -> None:
    pacote = pasta_projeto / "pacote_postagem"
    pacote.mkdir(parents=True, exist_ok=True)
    (pacote / "legenda.srt").write_text(srt.read_text(encoding="utf-8"), encoding="utf-8")
    if ass and ass.exists():
        (pacote / "legenda.ass").write_text(ass.read_text(encoding="utf-8"), encoding="utf-8")


def _audio_narracao(pasta_projeto: Path) -> Path | None:
    for nome in ["narracao.mp3", "narracao.wav"]:
        path = pasta_projeto / "audio" / nome
        if path.exists() and path.stat().st_size > 0:
            return path
    return None
