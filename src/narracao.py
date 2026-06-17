from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from src.utils import ambiente_utf8, atualizar_status, carregar_json_arquivo, normalizar_texto_portugues, obter_duracao_midia, salvar_json


VOZES_PT_BR = ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"]

DEFAULT_TTS = {
    "engine": "edge-tts",
    "fallback_engine": "pyttsx3",
    "voice": "pt-BR-AntonioNeural",
    "rate": "+0%",
    "volume": "+0%",
    "output_format": "mp3",
}


def garantir_config_tts(base_dir: Path) -> Path:
    config_path = base_dir / "config" / "tts.json"
    if not config_path.exists():
        salvar_json(config_path, DEFAULT_TTS)
    return config_path


def listar_vozes() -> list[str]:
    return VOZES_PT_BR[:]


def gerar_teste_voz(base_dir: Path, texto: str) -> Path | None:
    config = carregar_json_arquivo(garantir_config_tts(base_dir), default=DEFAULT_TTS)
    destino = base_dir / "saida" / "testes" / "teste_voz.mp3"
    destino.parent.mkdir(parents=True, exist_ok=True)
    log_path = base_dir / "saida" / "testes" / "teste_voz_erro.txt"
    voz = str(config.get("voice") or DEFAULT_TTS["voice"])
    print("Gerando narracao com edge-tts...")
    print(f"Voz selecionada: {voz}")
    try:
        _gerar_edge_tts(texto, destino, None, voz, str(config.get("rate", "+0%")), str(config.get("volume", "+0%")))
    except Exception as exc:
        log_path.write_text(f"Falha ao gerar teste com edge-tts:\n{exc}\n", encoding="utf-8")
        print(f"Falha ao gerar teste de voz. Log: {log_path}")
        return None
    _validar_audio(destino)
    print(f"Teste de voz gerado em: {destino}")
    return destino


def gerar_narracao(base_dir: Path, pasta_projeto: Path) -> Path | None:
    config_path = garantir_config_tts(base_dir)
    config = carregar_json_arquivo(config_path, default=DEFAULT_TTS)
    roteiro_path = pasta_projeto / "roteiro" / "roteiro_narrado.txt"
    if not roteiro_path.exists():
        roteiro_path = pasta_projeto / "roteiro.txt"
    texto = normalizar_texto_portugues(roteiro_path.read_text(encoding="utf-8"))
    audio_dir = pasta_projeto / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    log_path = pasta_projeto / "logs" / "narracao_erro.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _limpar_narracao_antiga(audio_dir)
    _limpar_legenda_antiga(pasta_projeto)

    engine = str(config.get("engine") or DEFAULT_TTS["engine"])
    if engine == "edge-tts":
        audio_path = audio_dir / "narracao.mp3"
        legenda_raw_path = pasta_projeto / "legendas" / "edge_tts_raw.srt"
        legenda_raw_path.parent.mkdir(parents=True, exist_ok=True)
        voz = str(config.get("voice") or DEFAULT_TTS["voice"])
        print("Gerando narracao com edge-tts...")
        print(f"Voz selecionada: {voz}")
        try:
            _gerar_edge_tts(
                texto,
                audio_path,
                legenda_raw_path,
                voz,
                str(config.get("rate", "+0%")),
                str(config.get("volume", "+0%")),
            )
            _validar_audio(audio_path)
            if legenda_raw_path.exists() and legenda_raw_path.stat().st_size > 0:
                _validar_legenda(legenda_raw_path)
            duracao = obter_duracao_midia(audio_path)
            atualizar_status(pasta_projeto, narracao="concluido")
            print(f"Narracao gerada em: {audio_path}")
            if duracao:
                print(f"Duracao da narracao: {duracao:.1f} segundos")
            return audio_path
        except Exception as exc:
            _remover_se_existir(audio_path)
            _remover_se_existir(legenda_raw_path)
            log_path.write_text(
                "Falha ao gerar narracao com edge-tts.\n"
                "Tentando fallback com pyttsx3.\n\n"
                f"Erro: {exc}\n",
                encoding="utf-8",
            )
            print("edge-tts falhou; tentando fallback com pyttsx3.")

    fallback = str(config.get("fallback_engine") or "pyttsx3")
    if fallback == "pyttsx3":
        return _gerar_fallback_pyttsx3(config, texto, pasta_projeto, log_path)

    atualizar_status(pasta_projeto, narracao="falhou")
    print("Narracao nao gerada; continuando sem audio.")
    return None


def _gerar_edge_tts(texto: str, destino: Path, legenda: Path | None, voz: str, rate: str, volume: str) -> None:
    comando = _comando_edge_tts(texto, destino, legenda, voz, rate, volume)
    if comando:
        try:
            subprocess.run(
                comando,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                env=ambiente_utf8(),
                timeout=180,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "edge-tts retornou erro.\n"
                f"STDOUT:\n{exc.stdout or ''}\n\n"
                f"STDERR:\n{exc.stderr or ''}"
            ) from exc
        return

    async def _run() -> None:
        import edge_tts

        communicate = edge_tts.Communicate(texto, voice=voz, rate=rate, volume=volume)
        await communicate.save(str(destino))

    asyncio.run(_run())


def _comando_edge_tts(texto: str, destino: Path, legenda: Path | None, voz: str, rate: str, volume: str) -> list[str] | None:
    edge_tts_exe = shutil.which("edge-tts")
    if edge_tts_exe:
        cmd = [edge_tts_exe]
    else:
        cmd = [sys.executable, "-m", "edge_tts"]
    cmd.extend(
        [
            "--voice",
            voz,
            "--text",
            texto,
            "--write-media",
            str(destino),
            "--rate",
            rate,
            "--volume",
            volume,
        ]
    )
    if legenda:
        cmd.extend(["--write-subtitles", str(legenda)])
    return cmd


def _limpar_narracao_antiga(audio_dir: Path) -> None:
    for nome in ["narracao.mp3", "narracao.wav"]:
        path = audio_dir / nome
        if path.exists():
            path.unlink()


def _limpar_legenda_antiga(pasta_projeto: Path) -> None:
    for path in [
        pasta_projeto / "legendas" / "edge_tts_raw.srt",
    ]:
        if path.exists():
            path.unlink()


def _remover_se_existir(path: Path) -> None:
    if path.exists():
        path.unlink()


def _gerar_fallback_pyttsx3(config: dict, texto: str, pasta_projeto: Path, log_path: Path) -> Path | None:
    audio_path = pasta_projeto / "audio" / "narracao.wav"
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", int(config.get("pyttsx3_rate", 180)))
        engine.setProperty("volume", float(config.get("pyttsx3_volume", 1.0)))
        _selecionar_voz(engine, str(config.get("voice_hint", "portuguese")))
        engine.save_to_file(texto, str(audio_path))
        engine.runAndWait()
        _validar_audio(audio_path)
    except Exception as exc:
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\nFallback pyttsx3 tambem falhou.\n")
            log.write(f"Erro: {exc}\n")
        atualizar_status(pasta_projeto, narracao="falhou")
        print("Narracao nao gerada; continuando sem audio.")
        return None

    duracao = obter_duracao_midia(audio_path)
    atualizar_status(pasta_projeto, narracao="concluido")
    print(f"Narracao gerada em: {audio_path}")
    if duracao:
        print(f"Duracao da narracao: {duracao:.1f} segundos")
    return audio_path


def _validar_audio(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Arquivo de audio nao foi criado corretamente: {path}")


def _validar_legenda(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Legenda sincronizada nao foi criada corretamente: {path}")


def _copiar_legenda_para_pacote(pasta_projeto: Path, legenda_path: Path) -> None:
    destino = pasta_projeto / "pacote_postagem" / "legenda.srt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(legenda_path.read_text(encoding="utf-8"), encoding="utf-8")


def _selecionar_voz(engine, voice_hint: str) -> None:
    hint = (voice_hint or "").lower()
    voices = engine.getProperty("voices") or []
    for voice in voices:
        nome = " ".join(
            [
                str(getattr(voice, "id", "")),
                str(getattr(voice, "name", "")),
                " ".join(str(lang) for lang in getattr(voice, "languages", []) or []),
            ]
        ).lower()
        if hint and hint in nome:
            engine.setProperty("voice", voice.id)
            return
    for voice in voices:
        nome = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
        if "portugu" in nome or "brazil" in nome or "brasil" in nome or "pt_" in nome or "pt-" in nome:
            engine.setProperty("voice", voice.id)
            return
