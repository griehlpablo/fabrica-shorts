from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from src.utils import ambiente_utf8, criar_slug, salvar_json


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}


def apis_configuradas() -> dict[str, bool]:
    return {
        "pexels": bool(os.environ.get("PEXELS_API_KEY")),
        "pixabay": bool(os.environ.get("PIXABAY_API_KEY")),
        "wikimedia": True,
    }


def buscar_midias_externas(base_dir: Path, pasta_projeto: Path, plano_visual: list[dict], fonte: str = "todas") -> list[dict]:
    if fonte == "local":
        return []
    fontes = []
    if fonte in {"todas", "externas", "pexels"}:
        fontes.append("pexels")
    if fonte in {"todas", "externas", "pixabay"}:
        fontes.append("pixabay")
    if fonte in {"todas", "externas", "wikimedia"}:
        fontes.append("wikimedia")

    registros = []
    erros = []
    for cena in plano_visual:
        for provedor in fontes:
            try:
                if provedor == "pexels":
                    registros.extend(_buscar_pexels(pasta_projeto, cena))
                elif provedor == "pixabay":
                    registros.extend(_buscar_pixabay(pasta_projeto, cena))
                elif provedor == "wikimedia":
                    registros.extend(_buscar_wikimedia(pasta_projeto, cena))
                time.sleep(0.2)
            except Exception as exc:
                erros.append({"provedor": provedor, "cena_id": cena["cena_id"], "erro": str(exc)})

    if erros:
        log = pasta_projeto / "logs" / "apis_midia_erro.json"
        salvar_json(log, erros)
    return registros


def _buscar_pexels(pasta_projeto: Path, cena: dict) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    query = _query(cena)
    headers = {"Authorization": key}
    if _quer_video(cena):
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({"query": query, "per_page": 3, "orientation": "portrait"})
        data = _json_get(url, headers=headers)
        return [_baixar_pexels_video(pasta_projeto, cena, item, query) for item in data.get("videos", [])[:3]]
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": query, "per_page": 3, "orientation": "portrait"})
    data = _json_get(url, headers=headers)
    return [_baixar_pexels_foto(pasta_projeto, cena, item, query) for item in data.get("photos", [])[:3]]


def _buscar_pixabay(pasta_projeto: Path, cena: dict) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    query = _query(cena)
    if _quer_video(cena):
        url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": key, "q": query, "per_page": 3, "safesearch": "true"})
        data = _json_get(url)
        return [_baixar_pixabay_video(pasta_projeto, cena, item, query) for item in data.get("hits", [])[:3]]
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode({"key": key, "q": query, "per_page": 3, "safesearch": "true", "image_type": "photo"})
    data = _json_get(url)
    return [_baixar_pixabay_foto(pasta_projeto, cena, item, query) for item in data.get("hits", [])[:3]]


def _buscar_wikimedia(pasta_projeto: Path, cena: dict) -> list[dict]:
    query = _query(cena)
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": 3,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "format": "json",
            "origin": "*",
        }
    )
    data = _json_get(url)
    pages = data.get("query", {}).get("pages", {})
    registros = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        file_url = info.get("url")
        if not file_url:
            continue
        ext = Path(urllib.parse.urlparse(file_url).path).suffix.lower()
        if ext not in IMAGE_EXTS:
            continue
        meta = info.get("extmetadata", {})
        licenca = _meta_val(meta, "LicenseShortName") or "Wikimedia Commons"
        autor = _meta_val(meta, "Artist")
        registros.append(
            _baixar_url(
                pasta_projeto,
                cena,
                file_url,
                f"wikimedia_{page.get('pageid')}{ext}",
                {
                    "provedor": "Wikimedia",
                    "url_origem": info.get("descriptionurl") or file_url,
                    "autor": _limpar_html(autor),
                    "licenca": _limpar_html(licenca),
                    "tipo": "imagem",
                    "query_usada": query,
                    "status": "aprovado" if licenca else "revisar",
                },
            )
        )
    return registros


def _baixar_pexels_video(pasta_projeto: Path, cena: dict, item: dict, query: str) -> dict:
    arquivos = sorted(item.get("video_files", []), key=lambda f: abs((f.get("height") or 0) - 1920))
    escolhido = next((f for f in arquivos if f.get("link")), arquivos[0] if arquivos else {})
    return _baixar_url(
        pasta_projeto,
        cena,
        escolhido.get("link"),
        f"pexels_{item.get('id')}.mp4",
        {
            "provedor": "Pexels",
            "url_origem": item.get("url"),
            "autor": item.get("user", {}).get("name", ""),
            "licenca": "Pexels License",
            "tipo": "video",
            "query_usada": query,
            "status": "aprovado",
        },
    )


def _baixar_pexels_foto(pasta_projeto: Path, cena: dict, item: dict, query: str) -> dict:
    return _baixar_url(
        pasta_projeto,
        cena,
        item.get("src", {}).get("large2x") or item.get("src", {}).get("large"),
        f"pexels_{item.get('id')}.jpg",
        {
            "provedor": "Pexels",
            "url_origem": item.get("url"),
            "autor": item.get("photographer", ""),
            "licenca": "Pexels License",
            "tipo": "imagem",
            "query_usada": query,
            "status": "aprovado",
        },
    )


def _baixar_pixabay_video(pasta_projeto: Path, cena: dict, item: dict, query: str) -> dict:
    videos = item.get("videos", {})
    escolhido = videos.get("medium") or videos.get("small") or videos.get("large") or {}
    return _baixar_url(
        pasta_projeto,
        cena,
        escolhido.get("url"),
        f"pixabay_{item.get('id')}.mp4",
        {
            "provedor": "Pixabay",
            "url_origem": item.get("pageURL"),
            "autor": item.get("user", ""),
            "licenca": "Pixabay Content License",
            "tipo": "video",
            "query_usada": query,
            "status": "aprovado",
        },
    )


def _baixar_pixabay_foto(pasta_projeto: Path, cena: dict, item: dict, query: str) -> dict:
    return _baixar_url(
        pasta_projeto,
        cena,
        item.get("largeImageURL") or item.get("webformatURL"),
        f"pixabay_{item.get('id')}.jpg",
        {
            "provedor": "Pixabay",
            "url_origem": item.get("pageURL"),
            "autor": item.get("user", ""),
            "licenca": "Pixabay Content License",
            "tipo": "imagem",
            "query_usada": query,
            "status": "aprovado",
        },
    )


def _baixar_url(pasta_projeto: Path, cena: dict, url: str | None, nome: str, meta: dict) -> dict:
    if not url:
        raise RuntimeError("URL de midia vazia")
    pasta = pasta_projeto / "midias_baixadas" / f"cena_{int(cena['cena_id']):02}"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / nome
    if not destino.exists() or destino.stat().st_size == 0:
        req = urllib.request.Request(url, headers={"User-Agent": "fabrica-shorts/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            destino.write_bytes(resp.read())
    return {
        "id_midia": f"cena_{int(cena['cena_id']):02}_{criar_slug(meta['provedor'])}_{destino.stem}",
        "cena_id": cena["cena_id"],
        "arquivo": str(destino.relative_to(pasta_projeto)),
        "baixado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "observacoes": "midia baixada automaticamente por API",
        **meta,
    }


def _json_get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "fabrica-shorts/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError("rate limit detectado")
        raise


def _query(cena: dict) -> str:
    termos = cena.get("palavras_chave_en") or cena.get("palavras_chave_pt") or []
    return " ".join(str(t) for t in termos[:4])


def _quer_video(cena: dict) -> bool:
    tipos = set(cena.get("tipo_de_midia_ideal", []))
    return bool(tipos & {"video_curto", "broll", "demonstracao_controlada"})


def _meta_val(meta: dict, chave: str) -> str:
    valor = meta.get(chave, {})
    return str(valor.get("value", "") if isinstance(valor, dict) else valor)


def _limpar_html(texto: str) -> str:
    return str(texto or "").replace("<span class=\"language", "").replace("</span>", "").strip()
