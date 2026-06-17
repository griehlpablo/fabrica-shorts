from __future__ import annotations

from pathlib import Path

from src.utils import carregar_json_arquivo, copiar_arquivo, salvar_json, atualizar_status


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
BUSCA_DIRS = ["imagens", "videos", "fundos", "sons", "musicas"]


def verificar_midias(base_dir: Path, pasta_projeto: Path) -> list[dict]:
    cenas = carregar_json_arquivo(pasta_projeto / "cenas.json", default=[])
    biblioteca = base_dir / "biblioteca"
    plano = []
    referencias = []

    for cena in cenas:
        encontrada = _encontrar_midia(biblioteca, cena.get("palavras_chave", []), cena.get("tipo_midia"))
        item = {
            "cena_id": cena["id"],
            "status": "pendente",
            "risco": "REVISAR",
            "origem": None,
            "arquivo_copiado": None,
            "observacao": "Nenhuma midia local compativel encontrada.",
        }

        if encontrada:
            destino = copiar_arquivo(encontrada, pasta_projeto / "midias" / "aprovadas")
            item.update(
                {
                    "status": "encontrada",
                    "risco": "SEGURA",
                    "origem": str(encontrada.relative_to(base_dir)),
                    "arquivo_copiado": str(destino.relative_to(pasta_projeto)),
                    "observacao": "Midia local copiada como aprovada.",
                }
            )
            cena["status_midia"] = "aprovada"
        else:
            cena["status_midia"] = "pendente"
            referencias.append(_referencia_manual(cena))

        plano.append(item)

    salvar_json(pasta_projeto / "cenas.json", cenas)
    salvar_json(pasta_projeto / "plano_midias.json", plano)
    (pasta_projeto / "links_sugeridos" / "referencias.txt").write_text(
        "\n\n".join(referencias) + ("\n" if referencias else ""),
        encoding="utf-8",
    )
    atualizar_status(pasta_projeto, midias="concluido" if plano else "pendente")
    return plano


def _encontrar_midia(biblioteca: Path, palavras: list[str], tipo_midia: str | None) -> Path | None:
    candidatos = []
    extensoes = VIDEO_EXTS if tipo_midia == "video" else IMAGE_EXTS | VIDEO_EXTS
    for subdir in BUSCA_DIRS:
        pasta = biblioteca / subdir
        if not pasta.exists():
            continue
        for arquivo in pasta.rglob("*"):
            if arquivo.is_file() and arquivo.suffix.lower() in extensoes:
                nome = arquivo.stem.lower()
                score = sum(1 for palavra in palavras if palavra and palavra in nome)
                if score:
                    candidatos.append((score, arquivo))
    if not candidatos:
        return None
    candidatos.sort(key=lambda item: (-item[0], str(item[1]).lower()))
    return candidatos[0][1]


def _referencia_manual(cena: dict) -> str:
    return (
        f"Cena {cena['id']}:\n"
        f"Midia sugerida: {cena.get('midia_necessaria', 'midia complementar')}.\n"
        "Status: PRECISA_AUTORIZACAO se vier de filme, serie, transmissao, podcast, "
        "canal de terceiro, musica comercial ou site externo.\n"
        "Motivo: use somente midias proprias, licenciadas ou autorizadas.\n"
        "Acao recomendada: substituir por midia livre/autoral ou preencher a licenca manualmente.\n"
        "Link: [preencher manualmente]"
    )
