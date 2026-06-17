from __future__ import annotations

import subprocess
import traceback
from pathlib import Path

from src.legendas import fonte_legenda, gerar_ass_de_srt, legenda_sincronizada, ler_srt
from src.utils import atualizar_status, carregar_json_arquivo, executar, ffmpeg_disponivel, ffprobe_disponivel, salvar_json


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
WIDTH = 1080
HEIGHT = 1920


def montar_video(base_dir: Path, pasta_projeto: Path) -> Path:
    cenas = carregar_json_arquivo(pasta_projeto / "cenas.json", default=[])
    audio_narracao = _audio_narracao(pasta_projeto)
    modo_narrado = _modo_narrado(pasta_projeto)
    if modo_narrado and not audio_narracao:
        raise RuntimeError(_mensagem_audio_narrado_ausente(pasta_projeto))
    if not ffmpeg_disponivel():
        raise RuntimeError("FFmpeg nao encontrado. Instale o FFmpeg e adicione ao PATH.")
    duracao_audio = _duracao_midia(audio_narracao) if audio_narracao else None
    if duracao_audio and cenas:
        cenas = _sincronizar_cenas_com_audio(pasta_projeto, cenas, duracao_audio)
        from src.legendas import gerar_legendas

        gerar_legendas(pasta_projeto)
    ass_path = _legenda_ass(pasta_projeto)
    usar_ass = bool(ass_path and legenda_sincronizada(pasta_projeto))
    ass_aplicado = False
    blocos_srt = [] if usar_ass else _blocos_srt_sincronizada(pasta_projeto)
    plano = carregar_json_arquivo(pasta_projeto / "plano_midias.json", default=[])
    plano_por_cena = {item["cena_id"]: item for item in plano}
    tema = _tema_projeto(pasta_projeto)
    render_dir = pasta_projeto / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    salvar_json(render_dir / "composicao_vertical.json", [])

    segmentos = []
    stats = {"cenas": len(cenas), "midias": 0, "fallback": 0}
    print(f"Montagem: {stats['cenas']} cenas detectadas.")

    for indice, cena in enumerate(cenas, start=1):
        print(f"Renderizando cena {indice}/{len(cenas)}...")
        item = plano_por_cena.get(cena["id"], {})
        arquivo_rel = item.get("arquivo_copiado") or item.get("midia_selecionada")
        arquivo = _resolver_arquivo_midia(base_dir, pasta_projeto, arquivo_rel)
        arquivo_valido = arquivo if arquivo and arquivo.exists() else None
        if item:
            cena.update(
                {
                    "funcao_narrativa": item.get("funcao_narrativa") or item.get("intencao_visual"),
                    "prioridade_visual": item.get("prioridade_visual", 5),
                    "fallback_variante": item.get("cena_id", cena.get("id")),
                    "layout_texto": item.get("layout_texto", "centro_alto"),
                    "texto_caixa": item.get("texto_caixa", "sem_caixa"),
                    "fallback_estilo": item.get("fallback_estilo", ""),
                }
            )
        try:
            if blocos_srt:
                segmentos_cena, usou_midia = _renderizar_cena_por_blocos_srt(
                    cena=cena,
                    arquivo=arquivo_valido,
                    pasta_projeto=pasta_projeto,
                    tema=tema,
                    total_cenas=len(cenas),
                    blocos_srt=blocos_srt,
                )
            elif item.get("segmentos_visuais") and len(item.get("segmentos_visuais", [])) > 1:
                segmentos_cena, usou_midia = _renderizar_segmentos_visuais(
                    cena=cena,
                    item=item,
                    base_dir=base_dir,
                    pasta_projeto=pasta_projeto,
                    tema=tema,
                    total_cenas=len(cenas),
                )
            else:
                segmento = render_dir / f"cena_{int(cena['id']):03}.mp4"
                _apagar_mp4_vazio(segmento)
                cena_render = dict(cena)
                if usar_ass:
                    cena_render["sem_legenda_visual"] = True
                usou_midia = _renderizar_cena(
                    cena=cena_render,
                    arquivo=arquivo_valido,
                    saida=segmento,
                    pasta_projeto=pasta_projeto,
                    tema=tema,
                    total_cenas=len(cenas),
                )
                segmentos_cena = [segmento]
        except RuntimeError as exc:
            _registrar_erro_montagem(
                pasta_projeto,
                etapa="renderizar_cena",
                cena_id=cena.get("id"),
                erro=str(exc),
                traceback_text=traceback.format_exc(),
            )
            raise RuntimeError(
                f"Falha ao renderizar a cena {cena.get('id')}. "
                f"Erro completo salvo em: {pasta_projeto / 'logs' / 'montagem_erro.txt'}"
            ) from exc
        _validar_segmentos_cena(segmentos_cena)
        segmento = f"{len(segmentos_cena)} segmentos gerados"
        print(f"Cena {indice} concluída: {segmento}")
        stats["midias" if usou_midia else "fallback"] += 1
        segmentos.extend(segmentos_cena)

    lista = render_dir / "concat.txt"
    lista.write_text(
        "\n".join(f"file '{_ffmpeg_path(path)}'" for path in segmentos),
        encoding="utf-8",
    )

    print("Juntando cenas...")
    saida = pasta_projeto / "pacote_postagem" / "video_final.mp4"
    video_sem_audio = render_dir / "video_sem_audio.mp4"
    _apagar_mp4_vazio(video_sem_audio)
    saida.parent.mkdir(parents=True, exist_ok=True)
    cmd_concat = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lista),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video_sem_audio),
    ]
    try:
        executar(
            cmd_concat,
            pasta_projeto / "logs" / "ffmpeg_concat_erro.log",
            etapa="concatenar_cenas",
        )
        _validar_video_gerado(video_sem_audio, cmd=cmd_concat)
        video_para_audio = video_sem_audio
        if usar_ass and ass_path:
            video_com_legenda = render_dir / "video_com_legenda_ass.mp4"
            _apagar_mp4_vazio(video_com_legenda)
            try:
                _aplicar_legenda_ass(pasta_projeto, video_sem_audio, ass_path, video_com_legenda)
                video_para_audio = video_com_legenda
                ass_aplicado = True
            except RuntimeError:
                raise RuntimeError("Falha ao aplicar legenda ASS. Veja logs/ass_erro.txt.")
        _gerar_video_final_com_audio(pasta_projeto, video_para_audio, saida, exigir_audio=modo_narrado)
    except RuntimeError as exc:
        _registrar_erro_montagem(
            pasta_projeto,
            etapa="concatenar_cenas",
            cena_id=None,
            erro=str(exc),
            traceback_text=traceback.format_exc(),
        )
        raise RuntimeError(
            f"Falha ao juntar as cenas. Erro completo salvo em: {pasta_projeto / 'logs' / 'montagem_erro.txt'}"
        ) from exc

    atualizar_status(pasta_projeto, status="montado", montagem="concluido")
    salvar_json(
        pasta_projeto / "render" / "montagem.json",
        {
            "video_final": str(saida),
            "legenda_ass": bool(usar_ass),
            "legenda_ass_aplicada": bool(ass_aplicado),
            "fallback_pillow_legenda": bool(blocos_srt) or (usar_ass and not ass_aplicado),
            **stats,
        },
    )
    print(f"Midias aprovadas usadas: {stats['midias']}")
    print(f"Cenas com fallback visual: {stats['fallback']}")
    _validar_video_final(saida, audio_narracao, exigir_audio=modo_narrado)
    print(f"Vídeo final gerado em: {saida}")
    return saida


def _renderizar_cena(
    cena: dict,
    arquivo: Path | None,
    saida: Path,
    pasta_projeto: Path,
    tema: str,
    total_cenas: int,
) -> bool:
    cena_id = int(cena["id"])

    if arquivo and arquivo.suffix.lower() in VIDEO_EXTS:
        duracao = f"{_duracao_cena(cena, tem_background=True):.3f}"
        overlay = pasta_projeto / "render" / f"overlay_{cena_id:03}.png"
        criar_imagem_cena(cena, overlay, tema, total_cenas, transparente=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(arquivo),
            "-i",
            str(overlay),
            "-t",
            duracao,
            "-filter_complex",
            "[0:v]split=2[bgsrc][fgsrc];"
            "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "gblur=sigma=20,eq=brightness=-0.35,setsar=1[bg];"
            "[fgsrc]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[tmp];[tmp][1:v]overlay=0:0,format=yuv420p,setsar=1[v]",
            "-map",
            "[v]",
            "-an",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            str(saida),
        ]
        try:
            _executar_cena(cmd, pasta_projeto, cena_id)
        except RuntimeError:
            _registrar_composicao_vertical(
                pasta_projeto,
                cena_id=cena_id,
                arquivo=arquivo,
                erro="erro_composicao_vertical; usando fallback de crop seguro",
                fallback=True,
                horizontal_blur=True,
                crop_seguro=True,
            )
            cmd = _cmd_video_crop_seguro(arquivo, overlay, saida, duracao)
            _executar_cena(cmd, pasta_projeto, cena_id)
        _validar_video_gerado(saida, cmd=cmd)
        _registrar_composicao_vertical(
            pasta_projeto,
            cena_id=cena_id,
            arquivo=arquivo,
            erro="",
            fallback=False,
            horizontal_blur=True,
            crop_seguro=True,
        )
        return True

    imagem_cena = pasta_projeto / "render" / f"cena_{cena_id:03}.png"
    background = arquivo if arquivo and arquivo.suffix.lower() in IMAGE_EXTS else None
    criar_imagem_cena(cena, imagem_cena, tema, total_cenas, transparente=background is not None)
    duracao = _duracao_cena(cena, tem_background=background is not None)
    frames = max(1, round(duracao * 30))
    if background:
        cmd = _cmd_imagem_ken_burns(background, imagem_cena, saida, frames, cena_id)
        _executar_cena(cmd, pasta_projeto, cena_id)
        _validar_video_gerado(saida, cmd=cmd)
        return True
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(imagem_cena),
        "-vf",
        "scale=1080:1920,setsar=1,format=yuv420p",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-r",
        "30",
        "-frames:v",
        str(frames),
        "-movflags",
        "+faststart",
        str(saida),
    ]
    _executar_cena(cmd, pasta_projeto, cena_id)
    _validar_video_gerado(saida, cmd=cmd)
    return background is not None


def _cmd_video_crop_seguro(arquivo: Path, overlay: Path, saida: Path, duracao: str) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(arquivo),
        "-i",
        str(overlay),
        "-t",
        duracao,
        "-filter_complex",
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "setsar=1[bg];[bg][1:v]overlay=0:0,format=yuv420p,setsar=1[v]",
        "-map",
        "[v]",
        "-an",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        str(saida),
    ]


def _renderizar_segmentos_visuais(
    cena: dict,
    item: dict,
    base_dir: Path,
    pasta_projeto: Path,
    tema: str,
    total_cenas: int,
) -> tuple[list[Path], bool]:
    render_dir = pasta_projeto / "render"
    cena_id = int(cena["id"])
    segmentos_plano = item.get("segmentos_visuais", [])
    total_duracao = max(0.5, float(cena.get("duracao", 5)))
    partes = max(1, len(segmentos_plano))
    segmentos = []
    usou_midia = False
    for idx, segmento_plano in enumerate(segmentos_plano, start=1):
        cena_sub = dict(cena)
        cena_sub["duracao"] = total_duracao / partes
        if idx > 1:
            cena_sub["texto_tela"] = ""
        arquivo = _resolver_arquivo_midia(base_dir, pasta_projeto, segmento_plano.get("midia"))
        saida = render_dir / f"cena_{cena_id:03}_visual_{idx:02}.mp4"
        _apagar_mp4_vazio(saida)
        usou_midia = _renderizar_cena(
            cena=cena_sub,
            arquivo=arquivo if arquivo and arquivo.exists() else None,
            saida=saida,
            pasta_projeto=pasta_projeto,
            tema=tema,
            total_cenas=total_cenas,
        ) or usou_midia
        segmentos.append(saida)
    return segmentos, usou_midia


def _cmd_imagem_ken_burns(background: Path, overlay: Path, saida: Path, frames: int, cena_id: int) -> list[str]:
    zoom = "min(zoom+0.0012,1.12)" if cena_id % 2 else "min(zoom+0.0010,1.10)"
    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"
    filtro = (
        "[0:v]scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
        f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d={frames}:s=1080x1920:fps=30,"
        "setsar=1,eq=brightness=-0.12[bg];"
        "[bg][1:v]overlay=0:0,format=yuv420p,setsar=1[v]"
    )
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(background),
        "-i",
        str(overlay),
        "-filter_complex",
        filtro,
        "-map",
        "[v]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-frames:v",
        str(frames),
        "-movflags",
        "+faststart",
        str(saida),
    ]


def _duracao_cena(cena: dict, tem_background: bool) -> float:
    duracao_original = float(cena.get("duracao", 5))
    if cena.get("duracao_ajustada_por_audio"):
        return max(0.5, duracao_original)
    if tem_background:
        return max(3, min(duracao_original, 5))
    return 4


def _renderizar_cena_por_blocos_srt(
    cena: dict,
    arquivo: Path | None,
    pasta_projeto: Path,
    tema: str,
    total_cenas: int,
    blocos_srt: list[dict],
) -> tuple[list[Path], bool]:
    render_dir = pasta_projeto / "render"
    cena_id = int(cena["id"])
    segmentos = []
    usou_midia = False

    for parte_idx, intervalo in enumerate(_intervalos_legenda_cena(cena, blocos_srt), start=1):
        duracao = max(0.05, intervalo["fim"] - intervalo["inicio"])
        cena_sub = dict(cena)
        cena_sub["duracao"] = duracao
        cena_sub["legenda_visual"] = intervalo["texto"]
        saida = render_dir / f"cena_{cena_id:03}_{parte_idx:03}.mp4"
        _apagar_mp4_vazio(saida)
        usou_midia = _renderizar_cena(
            cena=cena_sub,
            arquivo=arquivo,
            saida=saida,
            pasta_projeto=pasta_projeto,
            tema=tema,
            total_cenas=total_cenas,
        ) or usou_midia
        segmentos.append(saida)

    return segmentos, usou_midia


def _validar_segmentos_cena(segmentos_cena: list[Path]) -> None:
    if not segmentos_cena:
        raise RuntimeError("Nenhum segmento foi gerado para a cena.")
    for segmento in segmentos_cena:
        _validar_video_gerado(segmento)


def _intervalos_legenda_cena(cena: dict, blocos_srt: list[dict]) -> list[dict]:
    inicio_cena = float(cena.get("inicio_estimado", 0))
    fim_cena = inicio_cena + float(cena.get("duracao", 5))
    pontos = [inicio_cena, fim_cena]
    for bloco in blocos_srt:
        inicio = float(bloco["inicio"])
        fim = float(bloco["fim"])
        if _tem_sobreposicao(inicio_cena, fim_cena, inicio, fim):
            pontos.append(max(inicio_cena, inicio))
            pontos.append(min(fim_cena, fim))

    pontos = sorted({round(ponto, 3) for ponto in pontos if inicio_cena <= ponto <= fim_cena})
    intervalos = []
    for idx in range(len(pontos) - 1):
        inicio = pontos[idx]
        fim = pontos[idx + 1]
        if fim - inicio < 0.05:
            continue
        tempo_meio = inicio + ((fim - inicio) / 2)
        texto = _legenda_no_tempo(blocos_srt, tempo_meio)
        intervalos.append({"inicio": inicio, "fim": fim, "texto": texto})

    if not intervalos:
        intervalos.append({"inicio": inicio_cena, "fim": fim_cena, "texto": ""})
    return intervalos


def _legenda_no_tempo(blocos_srt: list[dict], tempo: float) -> str:
    for bloco in blocos_srt:
        if float(bloco["inicio"]) <= tempo < float(bloco["fim"]):
            return str(bloco["texto"])
    return ""


def _blocos_srt_sincronizada(pasta_projeto: Path) -> list[dict]:
    fonte = pasta_projeto / "legendas" / "fonte_legenda.txt"
    legenda = pasta_projeto / "legendas" / "legenda.srt"
    if not fonte.exists() or fonte.read_text(encoding="utf-8", errors="replace").strip() not in {"stable-ts", "edge-tts"}:
        return []
    return ler_srt(legenda)


def _audio_narracao(pasta_projeto: Path) -> Path | None:
    for nome in ["narracao.mp3", "narracao.wav"]:
        path = pasta_projeto / "audio" / nome
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def _modo_narrado(pasta_projeto: Path) -> bool:
    return (pasta_projeto / "roteiro" / "roteiro_narrado.txt").exists() or _fonte_legenda_sincronizada(pasta_projeto)


def _fonte_legenda_sincronizada(pasta_projeto: Path) -> bool:
    return fonte_legenda(pasta_projeto) in {"stable-ts", "edge-tts"}


def _mensagem_audio_narrado_ausente(pasta_projeto: Path) -> str:
    if _fonte_legenda_sincronizada(pasta_projeto):
        return (
            "ERRO: legenda sincronizada existe, mas audio/narracao.mp3 nao foi encontrado. Rode:\n"
            f"python main.py narracao --projeto {pasta_projeto.name}"
        )
    return (
        "ERRO: projeto narrado sem audio/narracao.mp3 ou audio/narracao.wav. Rode:\n"
        f"python main.py narracao --projeto {pasta_projeto.name}"
    )


def _sincronizar_cenas_com_audio(pasta_projeto: Path, cenas: list[dict], duracao_audio: float) -> list[dict]:
    duracoes = _distribuir_duracao_ponderada(duracao_audio, cenas)
    inicio = 0.0
    for cena, duracao in zip(cenas, duracoes):
        cena["inicio_estimado"] = round(inicio, 3)
        cena["duracao"] = round(duracao, 3)
        cena["duracao_ajustada_por_audio"] = True
        inicio += duracao
    salvar_json(pasta_projeto / "cenas.json", cenas)
    print(f"Duracao da narracao detectada: {duracao_audio:.1f} segundos")
    print("Duracao das cenas ajustada ao audio")
    return cenas


def _distribuir_duracao_ponderada(duracao_audio: float, cenas: list[dict]) -> list[float]:
    pesos = [max(0.1, float(cena.get("duracao", 5))) for cena in cenas]
    soma = sum(pesos) or len(cenas)
    duracoes = [duracao_audio * peso / soma for peso in pesos]
    diferenca = duracao_audio - sum(duracoes)
    if duracoes:
        duracoes[-1] += diferenca
    return duracoes


def _tem_sobreposicao(a_inicio: float, a_fim: float, b_inicio: float, b_fim: float) -> bool:
    return max(a_inicio, b_inicio) < min(a_fim, b_fim)


def _duracao_midia(path: Path | None) -> float | None:
    if not path:
        return None
    resultado = _ffprobe_valor(
        [
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    if not resultado:
        return None
    try:
        return float(resultado)
    except ValueError:
        return None


def _tem_stream(path: Path, tipo: str) -> bool:
    resultado = _ffprobe_valor(
        [
            "-select_streams",
            f"{tipo}:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return resultado == ("video" if tipo == "v" else "audio")


def _ffprobe_valor(args: list[str]) -> str | None:
    cmd = ["ffprobe", "-v", "error", *args]
    try:
        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if resultado.returncode != 0:
        return None
    return resultado.stdout.strip()


def _legenda_ass(pasta_projeto: Path) -> Path | None:
    ass = pasta_projeto / "legendas" / "legenda.ass"
    if ass.exists() and ass.stat().st_size > 0:
        return ass
    srt = pasta_projeto / "legendas" / "legenda.srt"
    if legenda_sincronizada(pasta_projeto) and srt.exists():
        return gerar_ass_de_srt(pasta_projeto, srt)
    return None


def _aplicar_legenda_ass(pasta_projeto: Path, entrada: Path, ass_path: Path, saida: Path) -> None:
    filtro = f"ass='{_ffmpeg_filter_path(ass_path)}'"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(entrada),
        "-vf",
        filtro,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-movflags",
        "+faststart",
        str(saida),
    ]
    try:
        executar(cmd, pasta_projeto / "logs" / "ass_erro.txt", etapa="aplicar_legenda_ass", timeout=120)
        _validar_video_gerado(saida, cmd=cmd)
        print("Legenda ASS aplicada com libass")
    except RuntimeError as exc:
        (pasta_projeto / "logs" / "ass_erro.txt").write_text(str(exc), encoding="utf-8")
        raise


def _ffmpeg_filter_path(path: Path) -> str:
    texto = str(path.resolve()).replace("\\", "/")
    texto = texto.replace(":", r"\:")
    texto = texto.replace("'", r"\'")
    return texto


def criar_imagem_cena(
    cena: dict,
    caminho_saida: Path,
    tema: str,
    total_cenas: int,
    background: Path | None = None,
    transparente: bool = False,
) -> Path:
    Image, ImageDraw, ImageFont, ImageFilter = _pillow()
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    if transparente:
        imagem = Image.new("RGBA", (WIDTH, HEIGHT), color=(0, 0, 0, 0))
    elif background:
        imagem = _preparar_background_imagem(background).convert("RGBA")
        escurecer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 92))
        imagem = Image.alpha_composite(imagem, escurecer)
    else:
        imagem = _criar_gradiente_escuro(cena)

    draw = ImageDraw.Draw(imagem)
    cena_id = int(cena["id"])
    titulo = _encurtar(tema, 48)
    texto_principal = _texto_visual_cena(cena)
    if cena.get("sem_legenda_visual"):
        legenda = ""
    elif "legenda_visual" in cena:
        legenda = _encurtar(cena.get("legenda_visual") or "", 150)
    else:
        legenda = _encurtar(cena.get("legenda_curta") or cena.get("narracao") or "", 150)

    fonte_principal = _fonte_para_linhas(texto_principal, largura=WIDTH - 160, max_linhas=2, tamanho_max=92, tamanho_min=72)
    fonte_legenda = _fonte_para_linhas(legenda, largura=WIDTH - 180, max_linhas=3, tamanho_max=52, tamanho_min=42)

    if not transparente:
        _desenhar_textura_sutil(draw, cena_id)

    _desenhar_texto_tela_dinamico(draw, texto_principal, fonte_principal, cena)
    _desenhar_legenda(draw, legenda, fonte_legenda)

    imagem.save(caminho_saida)
    return caminho_saida


def gerar_imagem_texto(
    texto: str,
    caminho_saida: Path,
    largura: int = WIDTH,
    altura: int = HEIGHT,
) -> Path:
    cena = {"id": 1, "texto_tela": texto, "narracao": texto}
    return criar_imagem_cena(cena, caminho_saida, texto, total_cenas=1)


def _desenhar_topo(draw, titulo: str, fonte_categoria, fonte_titulo, fonte_numero, cena_id: int, total_cenas: int) -> None:
    categoria = "CURIOSIDADE"
    cat_bbox = _text_bbox(draw, categoria, fonte_categoria)
    draw.rounded_rectangle((80, 84, 80 + (cat_bbox[2] - cat_bbox[0]) + 34, 134), radius=8, fill=(56, 189, 248, 44))
    _desenhar_texto_com_sombra(draw, (97, 94), categoria, fonte_categoria, fill=(125, 211, 252), shadow_offset=2)
    _desenhar_texto_com_sombra(draw, (80, 155), titulo.upper(), fonte_titulo, fill=(226, 232, 240), shadow_offset=2)
    numero = f"{cena_id:02}/{total_cenas:02}"
    bbox = _text_bbox(draw, numero, fonte_numero)
    draw.rounded_rectangle((842, 90, 1000, 140), radius=8, fill=(15, 23, 42, 150), outline=(255, 255, 255, 32), width=1)
    _desenhar_texto_com_sombra(draw, (921 - (bbox[2] - bbox[0]) // 2, 100), numero, fonte_numero, fill=(226, 232, 240), shadow_offset=2)


def _texto_visual_cena(cena: dict) -> str:
    texto = " ".join((cena.get("texto_tela") or "").split())
    return _encurtar(texto, 46)


def _fonte_para_linhas(texto: str, largura: int, max_linhas: int, tamanho_max: int, tamanho_min: int):
    for tamanho in range(tamanho_max, tamanho_min - 1, -2):
        fonte = _carregar_fonte(tamanho)
        linhas = _quebrar_texto_limitado(texto, fonte, largura, max_linhas)
        if len(linhas) <= max_linhas and all(_medir_texto(linha, fonte) <= largura for linha in linhas):
            return fonte
    return _carregar_fonte(tamanho_min)


def _desenhar_texto_tela_dinamico(draw, texto: str, fonte, cena: dict) -> None:
    if not texto:
        return
    layout = cena.get("layout_texto") or _layout_texto_padrao(cena)
    largura = WIDTH - 170
    if layout in {"topo_com_stroke", "topo_cinematografico"}:
        centro_y = 520
    elif layout == "centro_sem_caixa":
        centro_y = 770
    elif layout == "fechamento_central":
        centro_y = 860
    else:
        centro_y = 705 if int(cena.get("id", 1)) % 2 else 790
    _desenhar_caixa_texto(draw, texto, fonte, centro_y=centro_y, largura=largura, layout=layout, caixa=cena.get("texto_caixa", "sem_caixa"))


def _layout_texto_padrao(cena: dict) -> str:
    funcao = str(cena.get("funcao_narrativa", ""))
    if "cultura" in funcao:
        return "topo_cinematografico"
    if "explic" in funcao:
        return "topo_com_stroke"
    if "fechamento" in funcao:
        return "fechamento_central"
    return "centro_alto"


def _desenhar_caixa_texto(draw, texto: str, fonte, centro_y: int, largura: int, layout: str = "centro_alto", caixa: str = "sem_caixa") -> None:
    linhas = _quebrar_texto_limitado(texto, fonte, largura, max_linhas=2)
    espacamento = 18
    altura_total = _altura_linhas(draw, linhas, fonte, espacamento)
    y = centro_y - altura_total // 2
    if caixa == "caixa_pequena":
        max_largura = max(_medir_texto(linha, fonte) for linha in linhas)
        x1 = max(70, (WIDTH - max_largura) // 2 - 34)
        x2 = min(WIDTH - 70, (WIDTH + max_largura) // 2 + 34)
        rect = (x1, y - 24, x2, y + altura_total + 24)
        draw.rounded_rectangle(rect, radius=8, fill=(0, 0, 0, 96), outline=(255, 255, 255, 22), width=1)
    for linha in linhas:
        bbox = _text_bbox(draw, linha, fonte)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        cor = (255, 244, 178) if layout in {"mito_vs_realidade", "centro_sem_caixa", "fechamento_central"} else (255, 255, 255)
        _desenhar_texto_stroke(draw, (x, y), linha, fonte, fill=cor, stroke_width=4, shadow_offset=4)
        y += (bbox[3] - bbox[1]) + espacamento


def _desenhar_legenda(draw, texto: str, fonte) -> None:
    if not " ".join((texto or "").split()):
        return
    linhas = _quebrar_texto_limitado(texto, fonte, WIDTH - 180, max_linhas=2)
    espacamento = 16
    altura_total = _altura_linhas(draw, linhas, fonte, espacamento)
    y = 1245
    draw.rounded_rectangle((80, y - 46, WIDTH - 80, y + altura_total + 46), radius=10, fill=(0, 0, 0, 170), outline=(255, 255, 255, 28), width=1)
    for linha in linhas:
        bbox = _text_bbox(draw, linha, fonte)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        _desenhar_texto_com_sombra(draw, (x, y), linha, fonte, fill=(241, 245, 249), shadow_offset=3)
        y += (bbox[3] - bbox[1]) + espacamento


def _desenhar_progresso(draw, cena_id: int, total_cenas: int) -> None:
    return


def _desenhar_textura_sutil(draw, cena_id: int) -> None:
    for y in (318, 1110, 1660):
        offset = (cena_id * 19 + y) % 120
        draw.line((120 + offset, y, 960 - offset // 2, y), fill=(255, 255, 255, 10), width=1)
    for i in range(7):
        x = 105 + ((i * 97 + cena_id * 31) % 850)
        y = 300 + ((i * 173 + cena_id * 43) % 1260)
        draw.rectangle((x, y, x + 3, y + 3), fill=(255, 255, 255, 14))
    _desenhar_detalhes_visuais(draw, cena_id)


def _desenhar_detalhes_visuais(draw, cena_id: int) -> None:
    draw.ellipse((72, 1510, 128, 1566), fill=(56, 189, 248, 36))
    draw.ellipse((930, 345, 982, 397), fill=(250, 204, 21, 28))
    draw.line((80, 234, 1000, 234), fill=(255, 255, 255, 32), width=2)


def desenhar_texto_com_sombra(draw, pos: tuple[int, int], texto: str, fonte) -> None:
    _desenhar_texto_com_sombra(draw, pos, texto, fonte)


def _desenhar_texto_com_sombra(
    draw,
    pos: tuple[int, int],
    texto: str,
    fonte,
    fill: tuple[int, int, int] = (255, 255, 255),
    shadow_offset: int = 3,
) -> None:
    x, y = pos
    draw.text((x + shadow_offset, y + shadow_offset), texto, fill=(0, 0, 0, 175), font=fonte)
    draw.text((x, y), texto, fill=fill, font=fonte)


def _desenhar_texto_stroke(
    draw,
    pos: tuple[int, int],
    texto: str,
    fonte,
    fill: tuple[int, int, int] = (255, 255, 255),
    stroke_width: int = 3,
    shadow_offset: int = 3,
) -> None:
    x, y = pos
    draw.text(
        (x + shadow_offset, y + shadow_offset),
        texto,
        fill=(0, 0, 0, 150),
        font=fonte,
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 160),
    )
    draw.text((x, y), texto, fill=fill, font=fonte, stroke_width=stroke_width, stroke_fill=(0, 0, 0, 230))


def desenhar_caixa_texto(draw, texto: str, fonte, centro_y: int = 875, largura: int = 880) -> None:
    _desenhar_caixa_texto(draw, texto, fonte, centro_y, largura)


def quebrar_texto(texto: str, fonte, largura_maxima: int) -> list[str]:
    texto_limpo = " ".join((texto or "").replace("\n", " ").replace("\r", " ").split())
    if not texto_limpo:
        return ["Curiosidade"]

    linhas: list[str] = []
    linha_atual = ""
    for palavra in texto_limpo.split():
        tentativa = f"{linha_atual} {palavra}".strip()
        if _medir_texto(tentativa, fonte) <= largura_maxima:
            linha_atual = tentativa
        else:
            if linha_atual:
                linhas.append(linha_atual)
            linha_atual = palavra
    if linha_atual:
        linhas.append(linha_atual)
    return linhas[:5]


def _quebrar_texto_limitado(texto: str, fonte, largura_maxima: int, max_linhas: int) -> list[str]:
    linhas = quebrar_texto(texto, fonte, largura_maxima)
    if len(linhas) <= max_linhas:
        return linhas
    return linhas[:max_linhas]


def _preparar_background_imagem(path: Path):
    Image, _, _, ImageFilter = _pillow()
    imagem = Image.open(path).convert("RGB")
    proporcao_alvo = WIDTH / HEIGHT
    proporcao = imagem.width / imagem.height
    if proporcao > proporcao_alvo:
        nova_largura = int(imagem.height * proporcao_alvo)
        left = (imagem.width - nova_largura) // 2
        imagem = imagem.crop((left, 0, left + nova_largura, imagem.height))
    else:
        nova_altura = int(imagem.width / proporcao_alvo)
        top = (imagem.height - nova_altura) // 2
        imagem = imagem.crop((0, top, imagem.width, top + nova_altura))
    return imagem.resize((WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(radius=1.2))


def _criar_gradiente_escuro(cena: dict | None = None):
    Image, ImageDraw, _, _ = _pillow()
    imagem = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(imagem)
    cena_id = int((cena or {}).get("id", 1))
    estilo = (cena or {}).get("fallback_estilo") or _fallback_estilo_padrao(cena or {})
    paletas = {
        "documental_escuro": ((7, 9, 14), (34, 38, 48)),
        "cinema_dourado": ((12, 10, 8), (76, 55, 24)),
        "contraste_vermelho_escuro": ((10, 7, 10), (64, 20, 26)),
        "explicativo_azul_petroleo": ((6, 15, 18), (18, 70, 78)),
        "fechamento_preto_vinheta": ((2, 2, 4), (22, 22, 28)),
    }
    topo, base = paletas.get(estilo, paletas["documental_escuro"])
    for y in range(HEIGHT):
        t = y / max(HEIGHT - 1, 1)
        r = int(topo[0] * (1 - t) + base[0] * t)
        g = int(topo[1] * (1 - t) + base[1] * t)
        b = int(topo[2] * (1 - t) + base[2] * t)
        draw.line((0, y, WIDTH, y), fill=(r, g, b, 255))
    _aplicar_vinheta_e_grain(imagem, cena_id)
    return imagem


def _fallback_estilo_padrao(cena: dict) -> str:
    funcao = str(cena.get("funcao_narrativa", ""))
    if "cultura" in funcao:
        return "cinema_dourado"
    if "mito" in funcao or "contraste" in funcao:
        return "contraste_vermelho_escuro"
    if "explic" in funcao:
        return "explicativo_azul_petroleo"
    if "fechamento" in funcao:
        return "fechamento_preto_vinheta"
    return "documental_escuro"


def _aplicar_vinheta_e_grain(imagem, seed: int) -> None:
    Image, ImageDraw, _, ImageFilter = _pillow()
    vinheta = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(vinheta)
    for i in range(18):
        alpha = int(7 + i * 5)
        margem_x = int(i * WIDTH / 55)
        margem_y = int(i * HEIGHT / 55)
        draw.rectangle((margem_x, margem_y, WIDTH - margem_x, HEIGHT - margem_y), outline=(0, 0, 0, alpha), width=18)
    imagem.alpha_composite(vinheta.filter(ImageFilter.GaussianBlur(18)))
    grain = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grain)
    for i in range(900):
        x = (i * 37 + seed * 53) % WIDTH
        y = (i * 91 + seed * 29) % HEIGHT
        val = 255 if i % 3 else 0
        gdraw.point((x, y), fill=(val, val, val, 14))
    imagem.alpha_composite(grain)


def _carregar_fonte(tamanho: int):
    _, _, ImageFont, _ = _pillow()
    for fonte in [Path("C:/Windows/Fonts/arialbd.ttf"), Path("C:/Windows/Fonts/arial.ttf")]:
        if fonte.exists():
            return ImageFont.truetype(str(fonte), tamanho)
    return ImageFont.load_default()


def _altura_linhas(draw, linhas: list[str], fonte, espacamento: int) -> int:
    return sum(_text_bbox(draw, linha, fonte)[3] - _text_bbox(draw, linha, fonte)[1] for linha in linhas) + (
        espacamento * max(len(linhas) - 1, 0)
    )


def _medir_texto(texto: str, fonte) -> int:
    Image, ImageDraw, _, _ = _pillow()
    bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), texto, font=fonte)
    return bbox[2] - bbox[0]


def _text_bbox(draw, texto: str, fonte) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), texto, font=fonte)


def _encurtar(texto: str, limite: int) -> str:
    texto = " ".join((texto or "").split())
    return texto


def _tema_projeto(pasta_projeto: Path) -> str:
    tema_path = pasta_projeto / "tema.txt"
    if tema_path.exists():
        return tema_path.read_text(encoding="utf-8").strip()
    return pasta_projeto.name.replace("_", " ").title()


def _executar_cena(cmd: list[str], pasta_projeto: Path, cena_id: int) -> None:
    executar(
        cmd,
        pasta_projeto / "logs" / f"ffmpeg_cena_{cena_id}_erro.log",
        etapa="renderizar_cena",
        cena_id=cena_id,
    )


def _gerar_video_final_com_audio(pasta_projeto: Path, video_sem_audio: Path, saida: Path, exigir_audio: bool = False) -> None:
    audio = _audio_narracao(pasta_projeto)
    if not audio:
        if exigir_audio:
            raise RuntimeError(_mensagem_audio_narrado_ausente(pasta_projeto))
        saida.write_bytes(video_sem_audio.read_bytes())
        _validar_video_gerado(saida)
        return

    print("Adicionando áudio...")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_sem_audio),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(saida),
    ]
    try:
        executar(
            cmd,
            pasta_projeto / "logs" / "ffmpeg_audio_erro.log",
            etapa="adicionar_audio",
            timeout=120,
        )
    except RuntimeError:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_sem_audio),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(saida),
        ]
        executar(
            cmd,
            pasta_projeto / "logs" / "ffmpeg_audio_erro.log",
            etapa="adicionar_audio",
            timeout=120,
        )
    _validar_video_gerado(saida, cmd=cmd)


def _validar_video_final(saida: Path, audio_referencia: Path | None, exigir_audio: bool = False) -> None:
    if not ffprobe_disponivel():
        if exigir_audio:
            raise RuntimeError("ERRO: ffprobe nao encontrado; nao foi possivel validar a faixa de audio.")
        print("AVISO: ffprobe nao encontrado; validacao de streams pulada.")
        return
    if not _tem_stream(saida, "v"):
        raise RuntimeError("ERRO: video final gerado sem faixa de video.")
    if not _tem_stream(saida, "a"):
        mensagem = "ERRO: vídeo final gerado sem faixa de áudio."
        if exigir_audio:
            raise RuntimeError(mensagem)
        print(mensagem)
        return

    duracao_video = _duracao_midia(saida)
    duracao_audio = _duracao_midia(audio_referencia) if audio_referencia else None
    if duracao_video:
        print(f"Duração do vídeo final: {duracao_video:.1f} segundos")
    if duracao_audio:
        print(f"Duração do áudio: {duracao_audio:.1f} segundos")
    if duracao_video and duracao_audio:
        diferenca = abs(duracao_video - duracao_audio)
        print(f"Diferença vídeo/áudio: {diferenca:.2f} segundos")
        if diferenca > 1:
            print("AVISO: duração do vídeo e do áudio estão diferentes.")


def _validar_video_gerado(path: Path, cmd: list[str] | None = None) -> None:
    if not path.exists():
        mensagem = f"Arquivo de video nao foi criado: {path}"
        if cmd:
            mensagem += "\n\nComando executado:\n" + " ".join(cmd)
        raise RuntimeError(mensagem)
    if path.stat().st_size <= 0:
        _apagar_mp4_vazio(path)
        mensagem = f"Arquivo de video ficou com 0 bytes: {path}"
        if cmd:
            mensagem += "\n\nComando executado:\n" + " ".join(cmd)
        raise RuntimeError(mensagem)


def _apagar_mp4_vazio(path: Path) -> None:
    if path.suffix.lower() == ".mp4" and path.exists() and path.stat().st_size == 0:
        path.unlink()


def _ffmpeg_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def _resolver_arquivo_midia(base_dir: Path, pasta_projeto: Path, arquivo_rel: str | None) -> Path | None:
    if not arquivo_rel:
        return None
    path = Path(arquivo_rel)
    if path.is_absolute():
        return path
    candidato_projeto = pasta_projeto / path
    if candidato_projeto.exists():
        return candidato_projeto
    candidato_base = base_dir / path
    if candidato_base.exists():
        return candidato_base
    return candidato_projeto


def _registrar_composicao_vertical(
    pasta_projeto: Path,
    cena_id: int,
    arquivo: Path | None,
    erro: str,
    fallback: bool,
    horizontal_blur: bool,
    crop_seguro: bool,
) -> None:
    path = pasta_projeto / "render" / "composicao_vertical.json"
    registros = carregar_json_arquivo(path, default=[])
    registros.append(
        {
            "cena_id": cena_id,
            "midia": str(arquivo) if arquivo else "",
            "erro_composicao_vertical": erro,
            "fallback_renderizacao_usado": fallback,
            "midia_horizontal_adaptada_com_blur": horizontal_blur,
            "midia_vertical_usada_diretamente": False,
            "crop_seguro_aplicado": crop_seguro,
            "bordas_pretas_suspeitas": False,
        }
    )
    salvar_json(path, registros)


def _registrar_erro_montagem(
    pasta_projeto: Path,
    etapa: str,
    cena_id: int | str | None,
    erro: str,
    traceback_text: str | None = None,
) -> None:
    log_path = pasta_projeto / "logs" / "montagem_erro.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    partes = [
        "Etapa:",
        etapa,
        "",
        "Cena:",
        str(cena_id) if cena_id is not None else "nao informada",
        "",
        "Erro:",
        erro,
    ]
    if traceback_text:
        partes.extend(["", "Traceback:", traceback_text])
    log_path.write_text("\n".join(partes), encoding="utf-8")


def _pillow():
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ModuleNotFoundError as exc:
        raise RuntimeError("Pillow nao encontrado. Rode: pip install -r requirements.txt") from exc
    return Image, ImageDraw, ImageFont, ImageFilter
