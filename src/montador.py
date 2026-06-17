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
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
            "eq=brightness=-0.18[bg];[bg][1:v]overlay=0:0,format=yuv420p[v]",
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
        _executar_cena(cmd, pasta_projeto, cena_id)
        _validar_video_gerado(saida, cmd=cmd)
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
        "scale=1080:1920,format=yuv420p",
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


def _cmd_imagem_ken_burns(background: Path, overlay: Path, saida: Path, frames: int, cena_id: int) -> list[str]:
    zoom = "min(zoom+0.0012,1.12)" if cena_id % 2 else "min(zoom+0.0010,1.10)"
    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"
    filtro = (
        "[0:v]scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
        f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d={frames}:s=1080x1920:fps=30,"
        "eq=brightness=-0.12[bg];"
        "[bg][1:v]overlay=0:0,format=yuv420p[v]"
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

    fonte_categoria = _carregar_fonte(30)
    fonte_topo = _carregar_fonte(32)
    fonte_principal = _fonte_para_linhas(texto_principal, largura=WIDTH - 160, max_linhas=2, tamanho_max=92, tamanho_min=72)
    fonte_legenda = _fonte_para_linhas(legenda, largura=WIDTH - 180, max_linhas=3, tamanho_max=52, tamanho_min=42)
    fonte_pequena = _carregar_fonte(28)

    if not transparente:
        _desenhar_textura_sutil(draw, cena_id)

    _desenhar_topo(draw, titulo, fonte_categoria, fonte_topo, fonte_pequena, cena_id, total_cenas)
    _desenhar_caixa_texto(draw, texto_principal, fonte_principal, centro_y=835, largura=WIDTH - 160)
    _desenhar_legenda(draw, legenda, fonte_legenda)
    _desenhar_progresso(draw, cena_id, total_cenas)

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
    if not texto:
        texto = "Curiosidade"
    return _encurtar(texto, 46)


def _fonte_para_linhas(texto: str, largura: int, max_linhas: int, tamanho_max: int, tamanho_min: int):
    for tamanho in range(tamanho_max, tamanho_min - 1, -2):
        fonte = _carregar_fonte(tamanho)
        linhas = _quebrar_texto_limitado(texto, fonte, largura, max_linhas)
        if len(linhas) <= max_linhas and all(_medir_texto(linha, fonte) <= largura for linha in linhas):
            return fonte
    return _carregar_fonte(tamanho_min)


def _desenhar_caixa_texto(draw, texto: str, fonte, centro_y: int, largura: int) -> None:
    linhas = _quebrar_texto_limitado(texto, fonte, largura, max_linhas=2)
    espacamento = 24
    altura_total = _altura_linhas(draw, linhas, fonte, espacamento)
    y = centro_y - altura_total // 2
    caixa = (70, y - 62, WIDTH - 70, y + altura_total + 62)
    draw.rounded_rectangle(caixa, radius=10, fill=(0, 0, 0, 118), outline=(255, 255, 255, 34), width=2)
    draw.rectangle((90, caixa[1] + 18, 101, caixa[3] - 18), fill=(250, 204, 21, 210))
    for linha in linhas:
        bbox = _text_bbox(draw, linha, fonte)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        _desenhar_texto_com_sombra(draw, (x, y), linha, fonte, fill=(255, 255, 255), shadow_offset=5)
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
    x1, y1, x2, y2 = 80, 1814, 1000, 1824
    draw.rounded_rectangle((x1, y1, x2, y2), radius=5, fill=(255, 255, 255, 38))
    largura = int((x2 - x1) * cena_id / max(total_cenas, 1))
    draw.rounded_rectangle((x1, y1, x1 + largura, y2), radius=5, fill=(250, 204, 21, 230))


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
    paletas = [
        ((8, 14, 28), (20, 36, 80)),
        ((12, 12, 18), (44, 28, 54)),
        ((10, 18, 18), (18, 58, 52)),
        ((16, 14, 10), (58, 44, 22)),
        ((9, 12, 20), (42, 48, 62)),
    ]
    topo, base = paletas[cena_id % len(paletas)]
    for y in range(HEIGHT):
        t = y / max(HEIGHT - 1, 1)
        r = int(topo[0] * (1 - t) + base[0] * t)
        g = int(topo[1] * (1 - t) + base[1] * t)
        b = int(topo[2] * (1 - t) + base[2] * t)
        draw.line((0, y, WIDTH, y), fill=(r, g, b, 255))
    return imagem


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
