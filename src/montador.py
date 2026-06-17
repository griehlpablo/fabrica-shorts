from __future__ import annotations

import traceback
from pathlib import Path

from src.utils import atualizar_status, carregar_json_arquivo, executar, ffmpeg_disponivel, salvar_json


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
WIDTH = 1080
HEIGHT = 1920


def montar_video(base_dir: Path, pasta_projeto: Path) -> Path:
    if not ffmpeg_disponivel():
        raise RuntimeError("FFmpeg nao encontrado. Instale o FFmpeg e adicione ao PATH.")

    cenas = carregar_json_arquivo(pasta_projeto / "cenas.json", default=[])
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
        segmento = render_dir / f"cena_{int(cena['id']):03}.mp4"
        _apagar_mp4_vazio(segmento)
        item = plano_por_cena.get(cena["id"], {})
        arquivo_rel = item.get("arquivo_copiado")
        arquivo = pasta_projeto / arquivo_rel if arquivo_rel else None
        arquivo_valido = arquivo if arquivo and arquivo.exists() else None
        try:
            usou_midia = _renderizar_cena(
                cena=cena,
                arquivo=arquivo_valido,
                saida=segmento,
                pasta_projeto=pasta_projeto,
                tema=tema,
                total_cenas=len(cenas),
            )
        except RuntimeError as exc:
            _apagar_mp4_vazio(segmento)
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
        print(f"Cena {indice} concluída: {segmento}")
        stats["midias" if usou_midia else "fallback"] += 1
        segmentos.append(segmento)

    lista = render_dir / "concat.txt"
    lista.write_text(
        "\n".join(f"file '{_ffmpeg_path(path)}'" for path in segmentos),
        encoding="utf-8",
    )

    saida = pasta_projeto / "pacote_postagem" / "video_final.mp4"
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
        str(saida),
    ]
    try:
        executar(
            cmd_concat,
            pasta_projeto / "logs" / "ffmpeg_concat_erro.log",
            etapa="concatenar_cenas",
        )
        _validar_video_gerado(saida, cmd=cmd_concat)
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
    salvar_json(pasta_projeto / "render" / "montagem.json", {"video_final": str(saida), **stats})
    print(f"Midias aprovadas usadas: {stats['midias']}")
    print(f"Cenas com fallback visual: {stats['fallback']}")
    print(f"Video final: {saida}")
    return saida


def _renderizar_cena(
    cena: dict,
    arquivo: Path | None,
    saida: Path,
    pasta_projeto: Path,
    tema: str,
    total_cenas: int,
) -> bool:
    duracao_int = int(cena.get("duracao", 5))
    duracao = str(duracao_int)
    cena_id = int(cena["id"])

    if arquivo and arquivo.suffix.lower() in VIDEO_EXTS:
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
    criar_imagem_cena(cena, imagem_cena, tema, total_cenas, background=background)
    frames = duracao_int * 30
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
        imagem = _criar_gradiente_escuro()

    draw = ImageDraw.Draw(imagem)
    fonte_topo = _carregar_fonte(38)
    fonte_principal = _carregar_fonte(78)
    fonte_legenda = _carregar_fonte(42)
    fonte_pequena = _carregar_fonte(30)

    titulo = _encurtar(tema, 44)
    texto_principal = _encurtar(cena.get("texto_tela") or "Curiosidade", 58)
    legenda = _encurtar(cena.get("narracao") or "", 120)
    cena_id = int(cena["id"])

    _desenhar_topo(draw, titulo, fonte_topo, fonte_pequena, cena_id, total_cenas)
    _desenhar_caixa_texto(draw, texto_principal, fonte_principal, centro_y=875, largura=880)
    _desenhar_legenda(draw, legenda, fonte_legenda)
    _desenhar_progresso(draw, cena_id, total_cenas)

    if not transparente and not background:
        _desenhar_detalhes_visuais(draw, cena_id)

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


def _desenhar_topo(draw, titulo: str, fonte_titulo, fonte_numero, cena_id: int, total_cenas: int) -> None:
    _desenhar_texto_com_sombra(draw, (80, 112), titulo.upper(), fonte_titulo, fill=(232, 238, 248))
    numero = f"{cena_id:02}/{total_cenas:02}"
    bbox = _text_bbox(draw, numero, fonte_numero)
    draw.rounded_rectangle((842, 90, 1000, 146), radius=22, fill=(255, 255, 255, 34))
    _desenhar_texto_com_sombra(draw, (921 - (bbox[2] - bbox[0]) // 2, 103), numero, fonte_numero)


def _desenhar_caixa_texto(draw, texto: str, fonte, centro_y: int, largura: int) -> None:
    linhas = quebrar_texto(texto, fonte, largura)
    espacamento = 20
    altura_total = _altura_linhas(draw, linhas, fonte, espacamento)
    y = centro_y - altura_total // 2
    caixa = (70, y - 58, WIDTH - 70, y + altura_total + 58)
    draw.rounded_rectangle(caixa, radius=34, fill=(0, 0, 0, 112), outline=(255, 255, 255, 42), width=2)
    for linha in linhas:
        bbox = _text_bbox(draw, linha, fonte)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        _desenhar_texto_com_sombra(draw, (x, y), linha, fonte, shadow_offset=4)
        y += (bbox[3] - bbox[1]) + espacamento


def _desenhar_legenda(draw, texto: str, fonte) -> None:
    linhas = quebrar_texto(texto, fonte, 880)[:3]
    espacamento = 14
    altura_total = _altura_linhas(draw, linhas, fonte, espacamento)
    y = 1370
    draw.rounded_rectangle((70, y - 42, WIDTH - 70, y + altura_total + 42), radius=26, fill=(0, 0, 0, 145))
    for linha in linhas:
        bbox = _text_bbox(draw, linha, fonte)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        _desenhar_texto_com_sombra(draw, (x, y), linha, fonte, fill=(245, 247, 250), shadow_offset=3)
        y += (bbox[3] - bbox[1]) + espacamento


def _desenhar_progresso(draw, cena_id: int, total_cenas: int) -> None:
    x1, y1, x2, y2 = 90, 1778, 990, 1794
    draw.rounded_rectangle((x1, y1, x2, y2), radius=8, fill=(255, 255, 255, 42))
    largura = int((x2 - x1) * cena_id / max(total_cenas, 1))
    draw.rounded_rectangle((x1, y1, x1 + largura, y2), radius=8, fill=(56, 189, 248, 220))


def _desenhar_detalhes_visuais(draw, cena_id: int) -> None:
    cor = (56, 189, 248, 70) if cena_id % 2 else (148, 163, 184, 64)
    draw.ellipse((-180, 1180, 360, 1720), fill=cor)
    draw.ellipse((760, 230, 1190, 660), fill=(255, 255, 255, 24))
    draw.line((100, 320, 980, 320), fill=(255, 255, 255, 38), width=3)


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


def _criar_gradiente_escuro():
    Image, ImageDraw, _, _ = _pillow()
    imagem = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(imagem)
    for y in range(HEIGHT):
        t = y / max(HEIGHT - 1, 1)
        r = int(8 + 12 * (1 - t))
        g = int(14 + 22 * (1 - t))
        b = int(28 + 52 * (1 - t))
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
    if len(texto) <= limite:
        return texto
    return texto[: limite - 3].rstrip() + "..."


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
