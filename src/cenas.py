from __future__ import annotations

import re
from math import ceil

from src.utils import slugify


STOPWORDS = {
    "sobre",
    "como",
    "para",
    "porque",
    "quando",
    "muito",
    "pouco",
    "real",
    "tema",
    "voce",
    "mais",
    "menos",
    "entre",
    "quase",
    "sempre",
    "isso",
    "essa",
    "esse",
    "aqui",
}


TEXTOS_VISUAIS = [
    "A lenda por tras disso",
    "Hollywood exagerou?",
    "A realidade e diferente",
    "O detalhe que muda tudo",
    "Potencia nao e tudo",
    "Mito contra realidade",
    "Por que ficou famoso?",
    "O impacto na cultura pop",
    "A verdade surpreende",
]


def gerar_cenas(roteiro: str, tema: str) -> list[dict]:
    partes = _partes_narracao(roteiro, alvo=7)
    quantidade = max(6, min(9, len(partes)))
    partes = partes[:quantidade]
    duracao_por_cena = max(4, min(8, ceil(56 / quantidade)))

    cenas = []
    inicio = 0
    for idx, narracao in enumerate(partes, start=1):
        palavras = _palavras_chave(narracao, tema)
        duracao = duracao_por_cena
        cenas.append(
            {
                "id": idx,
                "inicio_estimado": inicio,
                "duracao": duracao,
                "narracao": narracao,
                "texto_tela": _texto_tela(idx, tema, palavras),
                "midia_necessaria": f"Imagem ou video relacionado a {', '.join(palavras[:3])}",
                "palavras_chave": palavras,
                "tipo_midia": "imagem" if idx % 3 else "video",
                "status_midia": "pendente",
            }
        )
        inicio += duracao
    return cenas


def _partes_narracao(roteiro: str, alvo: int) -> list[str]:
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", roteiro) if f.strip()]
    partes: list[str] = []
    for frase in frases:
        subpartes = [p.strip() for p in re.split(r",|;|:", frase) if p.strip()]
        if len(subpartes) > 1:
            partes.extend(_juntar_partes_curtas(subpartes))
        else:
            partes.append(frase)

    if len(partes) < 6:
        palavras = roteiro.split()
        tamanho = max(8, ceil(len(palavras) / alvo))
        partes = [" ".join(palavras[i : i + tamanho]).strip() for i in range(0, len(palavras), tamanho)]

    return [p if p.endswith((".", "!", "?")) else p + "." for p in partes if p]


def _juntar_partes_curtas(partes: list[str]) -> list[str]:
    resultado = []
    atual = ""
    for parte in partes:
        tentativa = f"{atual}, {parte}".strip(", ") if atual else parte
        if len(tentativa.split()) <= 16:
            atual = tentativa
        else:
            if atual:
                resultado.append(atual)
            atual = parte
    if atual:
        resultado.append(atual)
    return resultado


def _palavras_chave(texto: str, tema: str) -> list[str]:
    termos = []
    for parte in [tema, texto]:
        for raw in re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", parte.lower()):
            termo = slugify(raw)
            if termo and termo not in STOPWORDS and termo not in termos:
                termos.append(termo)
    return termos[:8] or ["curiosidade", "documentario", "fatos"]


def _texto_tela(idx: int, tema: str, palavras: list[str]) -> str:
    if idx == 1:
        return _titulo_curto_tema(tema)
    if idx - 2 < len(TEXTOS_VISUAIS):
        texto = TEXTOS_VISUAIS[idx - 2]
        if idx == 5 and palavras:
            texto = f"{palavras[0].replace('_', ' ').title()} nao e tudo"
        return texto
    if palavras:
        return palavras[0].replace("_", " ").title()
    return "Curiosidade"


def _titulo_curto_tema(tema: str) -> str:
    tema = " ".join(tema.split())
    if len(tema) <= 34:
        return tema
    return tema[:31].rstrip() + "..."
