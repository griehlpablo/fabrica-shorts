from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cenas import gerar_cenas
from src.curador_midia import verificar_midias
from src.legendas import gerar_legendas
from src.montador import montar_video
from src.pacote_postagem import gerar_pacote
from src.roteiro import gerar_roteiro
from src.utils import (
    carregar_json,
    criar_estrutura_projeto,
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


def cmd_midias(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    verificar_midias(BASE_DIR, pasta)
    print(f"Plano de midias atualizado em: {pasta / 'plano_midias.json'}")


def cmd_montar(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
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

    return parser


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
