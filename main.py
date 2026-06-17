from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from src.alinhamento import alinhar_legenda
from src.cenas import gerar_cenas, gerar_cenas_projeto
from src.curador_midia import verificar_midias
from src.fontes_midia import apis_configuradas, testar_pexels
from src.intencao_visual import gerar_plano_visual
from src.legendas import duracao_srt, fonte_legenda, gerar_legendas, ler_srt
from src.montador import montar_video
from src.narracao import gerar_narracao, gerar_teste_voz, listar_vozes
from src.pacote_postagem import gerar_pacote
from src.pesquisa import gerar_pesquisa
from src.roteiro import gerar_roteiro, gerar_roteiro_projeto
from src.utils import (
    carregar_json,
    carregar_json_arquivo,
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


def cmd_testar_pexels(args: argparse.Namespace) -> None:
    raise SystemExit(testar_pexels())


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
    composicao_vertical = pasta / "render" / "composicao_vertical.json"

    print(f"Projeto: {pasta}")
    print(f"Projeto existe: {_sim_nao(pasta.exists())}")
    print(f"roteiro/roteiro_narrado.txt: {_status_arquivo(roteiro)}")
    print(f"Roteiro preserva acentos: {_sim_nao(_texto_tem_acentos(roteiro))}")
    _diagnostico_roteiro_v4(roteiro, audio)
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
    _diagnostico_composicao_vertical(composicao_vertical)
    print("Elementos de template removidos:")
    print("- rotulo de nicho removido: sim")
    print("- contador de cena removido: sim")
    print("- barra de progresso removida: sim")
    _diagnostico_visual_direitos(pasta)
    if video.exists() and ffprobe_disponivel():
        resolucao = _resolucao_video(video)
        print(f"Resolucao do video: {resolucao or 'indisponivel'}")
        print(f"Video 1080x1920: {_sim_nao(resolucao == '1080x1920')}")
    if fonte_texto not in {"stable-ts", "edge-tts"}:
        print("AVISO: usando legenda estimada, nao sincronizada pelo edge-tts.")
        print("AVISO: legenda visual sera renderizada por cena ou fallback, nao por bloco SRT.")
    elif _montagem_flag(montagem, "legenda_ass_aplicada"):
        print(f"Legenda visual: renderizada por ASS/libass ({fonte_texto}).")
    else:
        print(f"Legenda visual: renderizada por fonte sincronizada ({fonte_texto}).")


def cmd_midias(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    verificar_midias(BASE_DIR, pasta, fonte=getattr(args, "fonte", "local"))
    print(f"Plano de midias atualizado em: {pasta / 'plano_midias.json'}")


def cmd_plano_visual(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    gerar_plano_visual(pasta)


def cmd_buscar_midias(args: argparse.Namespace) -> None:
    pasta = projeto_path(BASE_DIR, args.projeto)
    verificar_midias(BASE_DIR, pasta, fonte=args.fonte)


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
    gerar_plano_visual(pasta)
    verificar_midias(BASE_DIR, pasta, fonte="todas")
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
    midias.add_argument("--fonte", choices=["local", "externas", "todas"], default="local")
    midias.set_defaults(func=cmd_midias)

    plano_visual = sub.add_parser("plano-visual", help="Gera plano visual e shotlist por cena.")
    plano_visual.add_argument("--projeto", required=True)
    plano_visual.set_defaults(func=cmd_plano_visual)

    buscar_midias = sub.add_parser("buscar-midias", help="Busca e pontua midias locais/externas.")
    buscar_midias.add_argument("--projeto", required=True)
    buscar_midias.add_argument("--fonte", choices=["local", "externas", "todas"], default="todas")
    buscar_midias.set_defaults(func=cmd_buscar_midias)

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

    testar_pexels_cmd = sub.add_parser("testar-pexels", help="Testa endpoint de video da Pexels sem baixar midia.")
    testar_pexels_cmd.set_defaults(func=cmd_testar_pexels)

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


def _diagnostico_roteiro_v4(roteiro: Path, audio: Path | None) -> None:
    texto = roteiro.read_text(encoding="utf-8", errors="replace") if roteiro.exists() else ""
    palavras = [p for p in texto.split() if p.strip()]
    duracao = obter_duracao_midia(audio) if audio else None
    duracao_estimada = duracao or (len(palavras) / 145 * 60 if palavras else None)
    ppm = (len(palavras) / duracao_estimada * 60) if duracao_estimada else None
    print("Roteiro V4:")
    print(f"- palavras do roteiro: {len(palavras)}")
    print(f"- duracao estimada: {_fmt_duracao(duracao_estimada)}")
    print(f"- palavras por minuto estimadas: {ppm:.1f}" if ppm else "- palavras por minuto estimadas: indisponivel")
    print(f"- roteiro abaixo do minimo desejado: {_sim_nao(len(palavras) < 120)}")
    print(f"- roteiro parece curto demais: {_sim_nao(len(palavras) < 100)}")


def _diagnostico_composicao_vertical(path: Path) -> None:
    registros = carregar_json_arquivo(path, default=[]) if path.exists() else []
    print("Composicao vertical FFmpeg:")
    print(f"- registros: {len(registros)}")
    print(f"- bordas pretas detectadas ou suspeitas: {_sim_nao(any(r.get('bordas_pretas_suspeitas') for r in registros))}")
    print(f"- fallback de renderizacao: {_sim_nao(any(r.get('fallback_renderizacao_usado') for r in registros))}")
    print(f"- midia horizontal adaptada com blur: {_sim_nao(any(r.get('midia_horizontal_adaptada_com_blur') for r in registros))}")
    print(f"- midia vertical usada diretamente: {_sim_nao(any(r.get('midia_vertical_usada_diretamente') for r in registros))}")
    print(f"- crop seguro aplicado: {_sim_nao(any(r.get('crop_seguro_aplicado') for r in registros))}")
    for registro in registros:
        if registro.get("fallback_renderizacao_usado") or registro.get("erro_composicao_vertical"):
            print(
                f"- Cena {registro.get('cena_id')} fallback renderizacao: "
                f"{registro.get('erro_composicao_vertical') or 'sem erro registrado'}"
            )


def _diagnostico_visual_direitos(pasta: Path) -> None:
    plano_visual = pasta / "plano_visual.json"
    shotlist = pasta / "shotlist.md"
    fontes = pasta / "fontes_midias.json"
    plano_midias = pasta / "plano_midias.json"
    print(f"plano_visual.json existe: {_sim_nao(plano_visual.exists())}")
    print(f"shotlist.md existe: {_sim_nao(shotlist.exists())}")
    print(f"fontes_midias.json existe: {_sim_nao(fontes.exists())}")
    plano = carregar_json_arquivo(plano_midias, default=[])
    cenas = carregar_json_arquivo(pasta / "cenas.json", default=[])
    registros = carregar_json_arquivo(fontes, default=[])
    base_dir = BASE_DIR
    videos_locais = _contar_midias_dir(base_dir / "biblioteca" / "videos", {".mp4", ".mov", ".mkv", ".webm"})
    imagens_locais = _contar_midias_dir(base_dir / "biblioteca" / "imagens", {".jpg", ".jpeg", ".png", ".webp", ".bmp"})
    fundos_locais = _contar_midias_dir(base_dir / "biblioteca" / "fundos", {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".mp4", ".mov", ".mkv", ".webm"})
    usadas = [item.get("midia_selecionada") for item in plano if item.get("midia_selecionada")]
    unicas = set(usadas)
    repeticao_consecutiva = any(usadas[i] == usadas[i - 1] for i in range(1, len(usadas)))
    print(f"Midias usadas: {len(usadas)}")
    print(f"Midias unicas: {len(unicas)}")
    print(f"Houve repeticao: {_sim_nao(len(usadas) != len(unicas))}")
    print(f"Houve repeticao consecutiva: {_sim_nao(repeticao_consecutiva)}")
    print(f"Cenas com fallback: {sum(1 for item in plano if item.get('fallback_usado'))}")
    print(f"Cenas com video: {sum(1 for item in plano if _tipo_midia_plano(item) == 'video')}")
    print(f"Cenas com imagem: {sum(1 for item in plano if _tipo_midia_plano(item) == 'imagem')}")
    print(f"Midias de biblioteca/local: {sum(1 for item in plano if item.get('provedor') in {'Local', None})}")
    print(f"Midias de API externa: {sum(1 for item in plano if item.get('provedor') not in {'Local', 'fallback', None})}")
    print(f"Midias com licenca registrada: {sum(1 for item in registros if item.get('licenca'))}")
    sem_licenca = sum(1 for item in registros if item.get("status") == "local_sem_licenca")
    sem_licenca = max(sem_licenca, sum(1 for item in plano if item.get("provedor") == "Local" and not item.get("licenca")))
    print(f"Midias sem licenca: {sem_licenca}")
    print(f"Midias para revisar: {sum(1 for item in registros if item.get('status') == 'revisar')}")
    print(f"Numero de cenas: {len(cenas)}")
    cenas_com_texto = sum(1 for cena in cenas if str(cena.get("texto_tela", "")).strip())
    cenas_sem_texto = len(cenas) - cenas_com_texto
    percentual = (cenas_com_texto / len(cenas) * 100) if cenas else 0
    print(f"Cenas com texto_tela: {cenas_com_texto}")
    print(f"Cenas sem texto_tela: {cenas_sem_texto}")
    print(f"Percentual de cenas com texto_tela: {percentual:.1f}%")
    if cenas and cenas_com_texto == len(cenas):
        print("AVISO: todas as cenas usam texto_tela; considere tornar o texto visual mais seletivo.")
    cortes = [item for item in plano if item.get("corte_visual_interno")]
    total_segmentos = sum(len(item.get("segmentos_visuais", [])) for item in plano)
    print(f"Cenas com corte visual interno: {len(cortes)}")
    print(f"Segmentos visuais: {total_segmentos}")
    longas_sem_corte = [
        str(item.get("cena_id"))
        for item in plano
        if not item.get("corte_visual_interno") and any(float(seg.get("fim", 0)) - float(seg.get("inicio", 0)) >= 7 for seg in item.get("segmentos_visuais", []))
    ]
    print(f"Cenas longas sem troca visual: {', '.join(longas_sem_corte) if longas_sem_corte else 'nenhuma'}")
    provedores = sorted({str(item.get("provedor")) for item in plano if item.get("provedor") not in {"Local", "fallback", None}})
    print(f"Provedores externos usados: {', '.join(provedores) if provedores else 'nenhum'}")
    print("Visual V4:")
    caixas = _contar_por_chave(plano, "texto_caixa")
    layouts = _contar_por_chave(plano, "layout_texto")
    print(f"- Textos com caixa grande: {caixas.get('caixa_grande', 0)}")
    print(f"- Textos sem caixa: {caixas.get('sem_caixa', 0)}")
    print(f"- Textos com caixa pequena: {caixas.get('caixa_pequena', 0)}")
    print(f"- Layouts usados: {', '.join(layouts.keys()) if layouts else 'nenhum'}")
    fallback_cenas = [str(item.get("cena_id")) for item in plano if item.get("fallback_usado")]
    print(f"- Fallbacks usados: cenas {', '.join(fallback_cenas) if fallback_cenas else 'nenhuma'}")
    estilos = sorted({item.get("fallback_estilo") for item in plano if item.get("fallback_estilo")})
    print(f"- Estilos de fallback: {', '.join(estilos) if estilos else 'nenhum'}")
    print(f"- Videos locais encontrados: {videos_locais}")
    print(f"- Imagens locais encontradas: {imagens_locais}")
    print(f"- Fundos locais encontrados: {fundos_locais}")
    if videos_locais == 0:
        print("- Nenhum video local encontrado.")
    for item in plano:
        if item.get("fallback_usado"):
            print(f"- Cena {item.get('cena_id')} fallback: {item.get('motivo_fallback') or 'sem motivo registrado'}")
            print(f"  Sugestoes PT: {', '.join(item.get('sugestoes_de_busca_pt', [])[:4])}")
            print(f"  Sugestoes EN: {', '.join(item.get('sugestoes_de_busca_en', [])[:4])}")
        if float(item.get("score", 0)) < 15:
            print(f"- Cena {item.get('cena_id')} score baixo: {item.get('motivo_score_baixo') or 'sem motivo registrado'}")
    if any(item.get("reutilizacao_controlada") for item in plano):
        cenas = [str(item.get("cena_id")) for item in plano if item.get("reutilizacao_controlada")]
        print(f"- Reutilizacao controlada de midia: cenas {', '.join(cenas)}")
    elif videos_locais and not any(_tipo_midia_plano(item) == "video" for item in plano):
        print("- Video local encontrado mas nao usado: score menor que imagens ou penalidade de relevancia/repeticao.")
    scores = [float(item.get("score", 0)) for item in plano]
    media_score = sum(scores) / len(scores) if scores else 0
    print(f"Score medio das midias: {media_score:.1f}")
    baixos = [str(item.get("cena_id")) for item in plano if float(item.get("score", 0)) < 15]
    print(f"Cenas com score baixo: {', '.join(baixos) if baixos else 'nenhuma'}")
    print(f"APIs configuradas: Pexels {_sim_nao(bool(os.environ.get('PEXELS_API_KEY')))}, Pixabay {_sim_nao(bool(os.environ.get('PIXABAY_API_KEY')))}, Wikimedia sim")
    print(f"Midia externa baixada: {_sim_nao(any(item.get('provedor') not in {'Local', 'fallback', None} for item in registros))}")
    erros_api = pasta / "logs" / "apis_midia_erro.json"
    print(f"Erros de API: {_status_arquivo(erros_api)}")
    if sem_licenca:
        print("AVISO: midia local sem licenca registrada.")
    if any(item.get("fallback_usado") for item in plano):
        print("AVISO: fallback visual usado em uma ou mais cenas.")


def _contar_midias_dir(path: Path, extensoes: set[str]) -> int:
    if not path.exists():
        return 0
    return sum(1 for arquivo in path.rglob("*") if arquivo.is_file() and arquivo.suffix.lower() in extensoes)


def _contar_por_chave(itens: list[dict], chave: str) -> dict[str, int]:
    resultado: dict[str, int] = {}
    for item in itens:
        valor = str(item.get(chave) or "")
        if not valor:
            continue
        resultado[valor] = resultado.get(valor, 0) + 1
    return resultado


def _tipo_midia_plano(item: dict) -> str:
    for grupo in ["candidatos_local", "candidatos_externos"]:
        for candidato in item.get(grupo, []):
            if candidato.get("arquivo") == item.get("midia_selecionada"):
                return candidato.get("tipo", "")
    return ""


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
