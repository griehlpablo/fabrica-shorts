from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.fontes_midia import apis_configuradas, buscar_midias_externas
from src.intencao_visual import gerar_plano_visual
from src.utils import carregar_json_arquivo, criar_slug, ffprobe_disponivel, salvar_json, atualizar_status


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
BUSCA_DIRS = ["imagens", "videos", "fundos"]
STATUS_BLOQUEADOS = {"rejeitado", "precisa_autorizacao"}


def verificar_midias(base_dir: Path, pasta_projeto: Path, fonte: str = "local") -> list[dict]:
    plano_visual = _plano_visual(pasta_projeto)
    fontes_existentes = carregar_json_arquivo(pasta_projeto / "fontes_midias.json", default=[])
    externos = buscar_midias_externas(base_dir, pasta_projeto, plano_visual, fonte=fonte) if fonte in {"externas", "todas"} else []
    fontes = _mesclar_fontes(fontes_existentes, externos)
    catalogo = catalogar_midias(base_dir, pasta_projeto, fontes)
    plano = _montar_plano_midias(pasta_projeto, plano_visual, catalogo)

    fontes_atualizadas = carregar_json_arquivo(pasta_projeto / "fontes_midias.json", default=fontes)
    salvar_json(pasta_projeto / "fontes_midias.json", _mesclar_fontes(fontes_atualizadas, fontes))
    salvar_json(pasta_projeto / "plano_midias.json", plano)
    _salvar_referencias(pasta_projeto, plano)
    atualizar_status(pasta_projeto, midias="concluido" if plano else "pendente")
    print(f"Plano de midias atualizado em: {pasta_projeto / 'plano_midias.json'}")
    return plano


def catalogar_midias(base_dir: Path, pasta_projeto: Path, fontes: list[dict] | None = None) -> list[dict]:
    fontes = fontes or []
    por_arquivo = {registro.get("arquivo"): registro for registro in fontes if registro.get("arquivo")}
    itens = []
    for raiz in _raizes_busca(base_dir, pasta_projeto):
        if not raiz.exists():
            continue
        for arquivo in raiz.rglob("*"):
            if not arquivo.is_file() or arquivo.suffix.lower() not in IMAGE_EXTS | VIDEO_EXTS:
                continue
            rel = _relativo(arquivo, pasta_projeto, base_dir)
            origem = por_arquivo.get(rel) or por_arquivo.get(str(arquivo))
            itens.append(_catalogar_arquivo(arquivo, rel, origem))
    salvar_json(base_dir / "biblioteca" / "catalogo_midias.json", [item for item in itens if item["escopo"] == "biblioteca"])
    return itens


def _montar_plano_midias(pasta_projeto: Path, plano_visual: list[dict], catalogo: list[dict]) -> list[dict]:
    usados = set()
    anterior = None
    plano = []
    fontes_registro = []
    for cena in plano_visual:
        candidatos = [_avaliar_candidato(cena, item, usados, anterior) for item in catalogo]
        candidatos = [c for c in candidatos if c["status"] not in STATUS_BLOQUEADOS and not _tem_termo_evitado(cena, c)]
        candidatos.sort(key=lambda item: item["score"], reverse=True)
        escolhido = candidatos[0] if candidatos and candidatos[0]["score"] > 0 else None
        fallback_usado = escolhido is None
        if escolhido:
            usados.add(escolhido["arquivo"])
            anterior = escolhido["arquivo"]
            fontes_registro.append(_fonte_de_candidato(cena, escolhido))
        item = {
            "cena_id": cena["cena_id"],
            "texto_tela": cena["texto_tela"],
            "intencao_visual": cena["intencao_visual"],
            "tipo_de_midia_ideal": cena["tipo_de_midia_ideal"],
            "palavras_chave_pt": cena["palavras_chave_pt"],
            "palavras_chave_en": cena["palavras_chave_en"],
            "evitar": cena["evitar"],
            "prioridade_visual": cena["prioridade_visual"],
            "candidatos_local": [c for c in candidatos if c["provedor"] == "Local"][:8],
            "candidatos_externos": [c for c in candidatos if c["provedor"] != "Local"][:8],
            "midia_selecionada": escolhido["arquivo"] if escolhido else None,
            "arquivo_copiado": escolhido["arquivo"] if escolhido else None,
            "score": escolhido["score"] if escolhido else 0,
            "motivo_da_escolha": escolhido["motivo"] if escolhido else "fallback visual; nenhuma midia adequada encontrada",
            "provedor": escolhido["provedor"] if escolhido else "fallback",
            "licenca": escolhido["licenca"] if escolhido else "gerado localmente",
            "fallback_usado": fallback_usado,
            "status": "fallback" if fallback_usado else "selecionada",
        }
        plano.append(item)
    _atualizar_fontes_usadas(pasta_projeto, fontes_registro)
    return plano


def _avaliar_candidato(cena: dict, item: dict, usados: set[str], anterior: str | None) -> dict:
    texto = " ".join([item["nome"], " ".join(item.get("tags", [])), item.get("query_usada", "")]).lower()
    palavras = [*cena.get("palavras_chave_pt", []), *cena.get("palavras_chave_en", [])]
    relevancia = sum(8 for palavra in palavras if criar_slug(str(palavra)).replace("_", " ") in texto or str(palavra).lower() in texto)
    tipo = 0
    tipos_ideais = set(cena.get("tipo_de_midia_ideal", []))
    if item["tipo"] == "video" and tipos_ideais & {"video_curto", "broll", "demonstracao_controlada"}:
        tipo += 18
    if item["tipo"] == "imagem" and "imagem" in tipos_ideais:
        tipo += 8
    if "close" in tipos_ideais and any(t in texto for t in ["close", "detail", "detalhe", "revolver", "magnum"]):
        tipo += 10
    if "cinema" in tipos_ideais and any(t in texto for t in ["cinema", "movie", "film", "hollywood"]):
        tipo += 10
    qualidade = 10 if item["tipo"] == "video" else 4
    if item.get("orientacao") == "vertical":
        qualidade += 8
    licenca = 12 if item.get("status") == "aprovado" else -4 if item.get("status") == "local_sem_licenca" else 0
    diversidade = -80 if item["arquivo"] == anterior else -30 if item["arquivo"] in usados else 0
    penalidade = -60 if _tem_termo_evitado(cena, item) else 0
    score = relevancia + tipo + qualidade + licenca + diversidade + penalidade
    motivos = []
    if relevancia:
        motivos.append("palavras-chave compatíveis")
    if tipo:
        motivos.append("tipo de mídia adequado")
    if item.get("orientacao") == "vertical":
        motivos.append("orientação vertical")
    if licenca > 0:
        motivos.append("licença registrada")
    if diversidade < 0:
        motivos.append("penalidade por repetição")
    candidato = {
        "arquivo": item["arquivo"],
        "tipo": item["tipo"],
        "provedor": item.get("provedor", "Local"),
        "licenca": item.get("licenca", ""),
        "status": item.get("status", "local_sem_licenca"),
        "score": round(score, 2),
        "motivo": "; ".join(motivos) or "baixa correspondencia",
        "tags": item.get("tags", []),
        "orientacao": item.get("orientacao"),
    }
    return candidato


def _catalogar_arquivo(arquivo: Path, rel: str, origem: dict | None) -> dict:
    ext = arquivo.suffix.lower()
    tipo = "video" if ext in VIDEO_EXTS else "imagem"
    tags = _tags_arquivo(arquivo)
    largura, altura, duracao = _metadados_midia(arquivo)
    escopo = "projeto" if "midias_baixadas" in rel or rel.startswith("midias") else "biblioteca"
    return {
        "arquivo": rel,
        "nome": arquivo.stem.lower(),
        "extensao": ext,
        "tipo": tipo,
        "tags": tags,
        "slug": criar_slug(arquivo.stem),
        "largura": largura,
        "altura": altura,
        "duracao": duracao,
        "orientacao": _orientacao(largura, altura),
        "id_unico": str(arquivo.resolve()),
        "escopo": escopo,
        "provedor": (origem or {}).get("provedor", "Local"),
        "url_origem": (origem or {}).get("url_origem", ""),
        "autor": (origem or {}).get("autor", ""),
        "licenca": (origem or {}).get("licenca", ""),
        "status": (origem or {}).get("status", "local_sem_licenca"),
        "query_usada": (origem or {}).get("query_usada", ""),
    }


def _metadados_midia(path: Path) -> tuple[int | None, int | None, float | None]:
    if not ffprobe_disponivel():
        return None, None, None
    import subprocess

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=20,
        )
    except Exception:
        return None, None, None
    if result.returncode != 0:
        return None, None, None
    partes = [p for p in result.stdout.strip().split(",") if p]
    try:
        largura = int(float(partes[0])) if len(partes) > 0 else None
        altura = int(float(partes[1])) if len(partes) > 1 else None
        duracao = float(partes[2]) if len(partes) > 2 else None
        return largura, altura, duracao
    except ValueError:
        return None, None, None


def _plano_visual(pasta_projeto: Path) -> list[dict]:
    path = pasta_projeto / "plano_visual.json"
    if path.exists():
        return carregar_json_arquivo(path, default=[])
    return gerar_plano_visual(pasta_projeto)


def _raizes_busca(base_dir: Path, pasta_projeto: Path) -> list[Path]:
    return [*(base_dir / "biblioteca" / sub for sub in BUSCA_DIRS), pasta_projeto / "midias_baixadas", pasta_projeto / "midias" / "aprovadas"]


def _relativo(arquivo: Path, pasta_projeto: Path, base_dir: Path) -> str:
    try:
        return str(arquivo.relative_to(pasta_projeto)).replace("\\", "/")
    except ValueError:
        return str(arquivo.relative_to(base_dir)).replace("\\", "/")


def _tags_arquivo(path: Path) -> list[str]:
    slug = criar_slug(path.stem)
    return [parte for parte in slug.split("_") if len(parte) >= 3]


def _orientacao(largura: int | None, altura: int | None) -> str | None:
    if not largura or not altura:
        return None
    if altura > largura:
        return "vertical"
    if largura > altura:
        return "horizontal"
    return "quadrado"


def _tem_termo_evitado(cena: dict, item: dict) -> bool:
    texto = " ".join([item.get("arquivo", ""), item.get("nome", ""), " ".join(item.get("tags", []))]).lower()
    return any(str(termo).lower() in texto for termo in cena.get("evitar", []))


def _salvar_referencias(pasta_projeto: Path, plano: list[dict]) -> None:
    linhas = []
    for item in plano:
        if item["fallback_usado"]:
            linhas.append(f"Cena {item['cena_id']}: fallback visual; nenhuma midia adequada encontrada.")
        elif item.get("licenca") == "":
            linhas.append(f"Cena {item['cena_id']}: revisar direitos da midia {item['midia_selecionada']}.")
    destino = pasta_projeto / "links_sugeridos" / "referencias.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + ("\n" if linhas else ""), encoding="utf-8")


def _mesclar_fontes(existentes: list[dict], novos: list[dict]) -> list[dict]:
    vistos = {item.get("arquivo") for item in existentes}
    resultado = list(existentes)
    for item in novos:
        if item.get("arquivo") not in vistos:
            resultado.append(item)
            vistos.add(item.get("arquivo"))
    return resultado


def _fonte_de_candidato(cena: dict, escolhido: dict) -> dict:
    return {
        "id_midia": f"cena_{int(cena['cena_id']):02}_{criar_slug(escolhido['arquivo'])}",
        "cena_id": cena["cena_id"],
        "arquivo": escolhido["arquivo"],
        "provedor": escolhido.get("provedor", "Local"),
        "url_origem": "",
        "autor": "",
        "licenca": escolhido.get("licenca", ""),
        "tipo": escolhido.get("tipo", ""),
        "baixado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": escolhido.get("status", "local_sem_licenca"),
        "query_usada": "",
        "observacoes": "midia selecionada no plano de montagem",
    }


def _atualizar_fontes_usadas(pasta_projeto: Path, usadas: list[dict]) -> None:
    existentes = carregar_json_arquivo(pasta_projeto / "fontes_midias.json", default=[])
    salvar_json(pasta_projeto / "fontes_midias.json", _mesclar_fontes(existentes, usadas))
