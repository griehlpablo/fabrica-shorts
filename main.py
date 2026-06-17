from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from src.alinhamento import alinhar_legenda
from src.cenas import gerar_cenas, gerar_cenas_projeto
from src.curador_midia import verificar_midias
from src.legendas import duracao_srt, fonte_legenda, gerar_legendas, ler_srt
from src.montador import montar_video
from src.narracao import gerar_narracao, gerar_teste_voz, listar_vozes
from src.pacote_postagem import gerar_pacote
from src.pesquisa import gerar_pesquisa
from src.roteiro import gerar_roteiro, gerar_roteiro_projeto
from src.utils import (
    carregar_json,
    criar_estrutura_projeto,
    ambiente_utf8,
    ffprobe_disponivel,
    normalizar_texto_portugues,
    obter_duracao_midia,
    projeto_path,
    slugify,
    atualizar_status,
)


BASE_DIR = Path(__file__).resolve().parent


def cmd_criar(args: argparse.Namespace) -> None:
    if args.nicho != "curiosidade":
        raise SystemExit("Neste MVP apenas o nicho 'curiosidade' esta funcional.")

    nome_projeto = slugify(args.tema)
    pasta = criar_estrutura_projeto(BASE_DIR, nome_projeto, args.nicho, args.tema)

    roteiro = gerar_roteiro(args.tema)
    (pasta / "roteiro.txt").write_text(roteiro, encoding="utf-8")
    atualizar_status(pasta, status="criado", roteiro="concluido")

    cenas = gerar_cenas(roteiro, args.tema)
    (pasta / "cenas.json").write_text(
        carregar_json.dumps(cenas, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    atualizar_status(pasta, cenas="concluido")

    verificar_midias(BASE_DIR, pasta)
    print(f"Projeto criado: {pasta}")
    print("Proximo passo: python main.py montar --projeto", nome_projeto)


def cmd_pesquisar(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    gerar_pesquisa(pasta)


def cmd_roteiro(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    roteiro = gerar_roteiro_projeto(pasta)
    tema = (pasta / "tema.txt").read_text(encoding="utf-8").strip()
    gerar_cenas_projeto(pasta, tema)
    print(f"Roteiro salvo em: {pasta / 'roteiro' / 'roteiro_narrado.txt'}")


def cmd_narracao(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    gerar_narracao(BASE_DIR, pasta)


def cmd_alinhar(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    alinhar_legenda(BASE_DIR, pasta)


def cmd_testar_texto(args: argparse.Namespace) -> None:
    texto = "força, coração, ação, munição, pressão, histórico, público, revólver, não, então"
    destino = BASE_DIR / "saida" / "testes" / "texto_portugues.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto + "\n", encoding="utf-8")
    lido = normalizar_texto_portugues(destino.read_text(encoding="utf-8"))
    print(f"Arquivo: {destino}")
    print(lido)
    for palavra in ["força", "coração", "ação", "munição", "revólver"]:
        print(f"{palavra}: {'preservado' if palavra in lido else 'PERDIDO'}")


def cmd_vozes(args: argparse.Namespace) -> None:
    print("Vozes sugeridas para curiosidade_narrada:")
    for voz in listar_vozes():
        print(f"- {voz}")


def cmd_testar_voz(args: argparse.Namespace) -> None:
    gerar_teste_voz(BASE_DIR, args.texto)


def cmd_diagnostico(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    audio = _audio_oficial(pasta)
    roteiro = pasta / "roteiro" / "roteiro_narrado.txt"
    legenda = pasta / "legendas" / "legenda.srt"
    legenda_ass = pasta / "legendas" / "legenda.ass"
    legenda_pacote = pasta / "pacote_postagem" / "legenda.srt"
    video = pasta / "pacote_postagem" / "video_final.mp4"
    montagem = pasta / "render" / "montagem.json"

    print(f"Projeto: {pasta}")
    print(f"Projeto existe: {_sim_nao(pasta.exists())}")
    print(f"roteiro/roteiro_narrado.txt: {_status_arquivo(roteiro)}")
    print(f"Roteiro preserva acentos: {_sim_nao(_texto_tem_acentos(roteiro))}")
    print(f"audio/narracao.mp3: {_status_arquivo(pasta / 'audio' / 'narracao.mp3')}")
    print(f"audio/narracao.wav: {_status_arquivo(pasta / 'audio' / 'narracao.wav')}")
    print(f"Caminho do audio: {audio if audio else 'nao encontrado'}")
    print(f"legendas/legenda.srt: {_status_arquivo(legenda)}")
    print(f"legendas/legenda.ass: {_status_arquivo(legenda_ass)}")
    print(f"pacote_postagem/legenda.srt: {_status_arquivo(legenda_pacote)}")
    print(f"pacote_postagem/video_final.mp4: {_status_arquivo(video)}")

    duracao_audio = obter_duracao_midia(audio) if audio else None
    duracao_video = obter_duracao_midia(video) if video.exists() else None
    print(f"Duração do áudio: {_fmt_duracao(duracao_audio)}")
    print(f"Duração do vídeo: {_fmt_duracao(duracao_video)}")
    if duracao_audio is not None and duracao_video is not None:
        print(f"Diferença: {abs(duracao_video - duracao_audio):.2f}s")

    if video.exists():
        if ffprobe_disponivel():
            streams = _streams_video(video)
            print(f"Streams do vídeo: {', '.join(streams) if streams else 'indisponível'}")
        else:
            streams = []
            print("Streams do vídeo: indisponível (ffprobe nao encontrado)")
        if ffprobe_disponivel() and "audio" not in streams:
            print("ERRO: vídeo final gerado sem faixa de áudio.")

    oficial = legenda if legenda.exists() else legenda_pacote if legenda_pacote.exists() else None
    print(f"Legenda oficial: {oficial if oficial else 'nao encontrada'}")
    fonte = pasta / "legendas" / "fonte_legenda.txt"
    fonte_texto = ""
    if fonte.exists():
        fonte_texto = fonte.read_text(encoding="utf-8", errors="replace").strip()
        print(f"Fonte da legenda: {fonte_texto}")
    blocos_srt = ler_srt(legenda)
    print(f"Blocos SRT: {len(blocos_srt)}")
    print(f"Duração total do SRT: {_fmt_duracao(duracao_srt(blocos_srt))}")
    print(f"Fonte normalizada da legenda: {fonte_legenda(pasta) or 'nao informada'}")
    print(f"Legenda preserva acentos: {_sim_nao(_texto_tem_acentos(legenda))}")
    print(f"Legenda ASS existe: {_sim_nao(legenda_ass.exists() and legenda_ass.stat().st_size > 0)}")
    print(f"Legenda contem reticencias: {_sim_nao(_texto_contem_reticencias(legenda) or _texto_contem_reticencias(legenda_ass))}")
    if _texto_contem_reticencias(legenda) or _texto_contem_reticencias(legenda_ass):
        print("AVISO: legenda contem reticencias. Verifique se sao do roteiro original ou truncamento indevido.")
    print(f"Legenda renderizada por ASS/libass: {_sim_nao(_montagem_flag(montagem, 'legenda_ass_aplicada'))}")
    print(f"Fallback Pillow usado: {_sim_nao(_montagem_flag(montagem, 'fallback_pillow_legenda'))}")
    if video.exists() and ffprobe_disponivel():
        resolucao = _resolucao_video(video)
        print(f"Resolucao do video: {resolucao or 'indisponivel'}")
        print(f"Video 1080x1920: {_sim_nao(resolucao == '1080x1920')}")
    if fonte_texto not in {"stable-ts", "edge-tts"}:
        print("AVISO: usando legenda estimada, nao sincronizada pelo edge-tts.")
        print("AVISO: legenda visual sera renderizada por cena ou fallback, nao por bloco SRT.")
    else:
        print("Legenda visual: renderizada por bloco SRT.")


def cmd_midias(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    verificar_midias(BASE_DIR, pasta)
    print(f"Plano de midias atualizado em: {pasta / 'plano_midias.json'}")


def cmd_montar(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    if _projeto_narrado(pasta) and not _audio_oficial(pasta):
        raise SystemExit(_mensagem_audio_narrado_ausente(pasta))
    gerar_legendas(pasta)
    montar_video(BASE_DIR, pasta)
    print(f"Video final gerado em: {pasta / 'pacote_postagem' / 'video_final.mp4'}")


def cmd_pacote(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    gerar_pacote(pasta)
    print(f"Pacote de postagem gerado em: {pasta / 'pacote_postagem'}")


def cmd_tudo(args: argparse.Namespace) -> None:
    nome_projeto = slugify(args.tema)
    cmd_criar(args)
    cmd_montar(argparse.Namespace(projeto=nome_projeto))
    cmd_pacote(argparse.Namespace(projeto=nome_projeto))
    print("Fluxo completo finalizado.")


def cmd_narrado(args: argparse.Namespace) -> None:
    if args.nicho != "curiosidade":
        raise SystemExit("Neste MVP apenas o nicho 'curiosidade' esta funcional.")

    nome_projeto = slugify(args.tema)
    pasta = criar_estrutura_projeto(BASE_DIR, nome_projeto, args.nicho, args.tema)
    print(f"Projeto criado: {pasta}")

    gerar_pesquisa(pasta)
    gerar_roteiro_projeto(pasta)
    gerar_cenas_projeto(pasta, args.tema)
    verificar_midias(BASE_DIR, pasta)
    print("Midias locais verificadas")
    gerar_narracao(BASE_DIR, pasta)
    if _projeto_narrado(pasta) and not _audio_oficial(pasta):
        raise SystemExit(_mensagem_audio_narrado_ausente(pasta))
    alinhar_legenda(BASE_DIR, pasta)
    montar_video(BASE_DIR, pasta)
    gerar_pacote(pasta)
    print(f"Fluxo narrado finalizado: {pasta / 'pacote_postagem' / 'video_final.mp4'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Fabrica local de videos curtos verticais.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    criar = sub.add_parser("criar", help="Cria projeto, roteiro, cenas e plano de midias.")
    criar.add_argument("--nicho", required=True)
    criar.add_argument("--tema", required=True)
    criar.set_defaults(func=cmd_criar)

    midias = sub.add_parser("midias", help="Reverifica midias locais para um projeto.")
    midias.add_argument("--projeto", required=True)
    midias.set_defaults(func=cmd_midias)

    pesquisar = sub.add_parser("pesquisar", help="Gera briefing e pendencias factuais locais.")
    pesquisar.add_argument("--projeto", required=True)
    pesquisar.set_defaults(func=cmd_pesquisar)

    roteiro_cmd = sub.add_parser("roteiro", help="Gera roteiro narrado e cenas.")
    roteiro_cmd.add_argument("--projeto", required=True)
    roteiro_cmd.set_defaults(func=cmd_roteiro)

    narracao = sub.add_parser("narracao", help="Gera narracao com edge-tts e fallback local.")
    narracao.add_argument("--projeto", required=True)
    narracao.set_defaults(func=cmd_narracao)

    alinhar = sub.add_parser("alinhar", help="Alinha audio e roteiro com stable-ts e gera SRT/ASS.")
    alinhar.add_argument("--projeto", required=True)
    alinhar.set_defaults(func=cmd_alinhar)

    testar_texto = sub.add_parser("testar-texto", help="Valida preservacao de acentos em UTF-8.")
    testar_texto.set_defaults(func=cmd_testar_texto)

    vozes = sub.add_parser("vozes", help="Lista vozes sugeridas para edge-tts.")
    vozes.set_defaults(func=cmd_vozes)

    testar_voz = sub.add_parser("testar-voz", help="Gera um teste curto de narracao.")
    testar_voz.add_argument("--texto", required=True)
    testar_voz.set_defaults(func=cmd_testar_voz)

    diagnostico = sub.add_parser("diagnostico", help="Mostra duracoes, streams e arquivos do projeto.")
    diagnostico.add_argument("--projeto", required=True)
    diagnostico.set_defaults(func=cmd_diagnostico)

    montar = sub.add_parser("montar", help="Monta video vertical e gera legenda.")
    montar.add_argument("--projeto", required=True)
    montar.set_defaults(func=cmd_montar)

    pacote = sub.add_parser("pacote", help="Gera arquivos de publicacao.")
    pacote.add_argument("--projeto", required=True)
    pacote.set_defaults(func=cmd_pacote)

    tudo = sub.add_parser("tudo", help="Roda o fluxo MVP completo.")
    tudo.add_argument("--nicho", required=True)
    tudo.add_argument("--tema", required=True)
    tudo.set_defaults(func=cmd_tudo)

    narrado = sub.add_parser("narrado", help="Roda o fluxo curiosidade narrada completo.")
    narrado.add_argument("--nicho", required=True)
    narrado.add_argument("--tema", required=True)
    narrado.set_defaults(func=cmd_narrado)

    return parser


def _audio_oficial(pasta: Path) -> Path | None:
    for nome in ["narracao.mp3", "narracao.wav"]:
        path = pasta / "audio" / nome
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def _projeto_narrado(pasta: Path) -> bool:
    return (pasta / "roteiro" / "roteiro_narrado.txt").exists() or _fonte_legenda_sincronizada(pasta)


def _fonte_legenda_sincronizada(pasta: Path) -> bool:
    return fonte_legenda(pasta) in {"stable-ts", "edge-tts"}


def _mensagem_audio_narrado_ausente(pasta: Path) -> str:
    if _fonte_legenda_sincronizada(pasta):
        return (
            "ERRO: legenda sincronizada existe, mas audio/narracao.mp3 nao foi encontrado. Rode:\n"
            f"python main.py narracao --projeto {pasta.name}"
        )
    return (
        "ERRO: projeto narrado sem audio/narracao.mp3 ou audio/narracao.wav. Rode:\n"
        f"python main.py narracao --projeto {pasta.name}"
    )


def _sim_nao(valor: bool) -> str:
    return "sim" if valor else "nao"


def _status_arquivo(path: Path) -> str:
    if not path.exists():
        return "nao"
    tamanho = path.stat().st_size
    if tamanho <= 0:
        return "sim, mas vazio"
    return f"sim ({tamanho} bytes)"


def _fmt_duracao(valor: float | None) -> str:
    return f"{valor:.2f}s" if valor is not None else "indisponivel"


def _texto_tem_acentos(path: Path) -> bool:
    if not path.exists():
        return False
    texto = path.read_text(encoding="utf-8", errors="replace")
    return any(ch in texto for ch in "áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ")


def _texto_contem_reticencias(path: Path) -> bool:
    if not path.exists():
        return False
    return "..." in path.read_text(encoding="utf-8", errors="replace")


def _montagem_flag(path: Path, chave: str) -> bool:
    if not path.exists():
        return False
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(dados.get(chave))


def _streams_video(video: Path) -> list[str]:
    try:
        resultado = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=ambiente_utf8(),
            timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []
    if resultado.returncode != 0:
        return []
    return [linha.strip() for linha in resultado.stdout.splitlines() if linha.strip()]


def _resolucao_video(video: Path) -> str | None:
    try:
        resultado = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=ambiente_utf8(),
            timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if resultado.returncode != 0:
        return None
    return resultado.stdout.strip() or None


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except FileNotFoundError as exc:
        print(f"Arquivo ou pasta nao encontrado: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
