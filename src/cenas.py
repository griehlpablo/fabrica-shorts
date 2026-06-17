from __future__ import annotations

import re
from math import ceil

from src.utils import criar_slug, normalizar_texto_portugues


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
    "você",
    "mais",
    "menos",
    "entre",
    "quase",
    "sempre",
    "isso",
    "essa",
    "esse",
    "aqui",
    "aquele",
    "aquela",
}


TEXTOS_VISUAIS = {
    "gancho": "A LENDA COMEÇA AQUI",
    "cultura_pop": "A TELA AMPLIFICOU",
    "mito_vs_realidade": "MITO CONTRA REALIDADE",
    "explicacao": "",
    "contraste": "FORA DA FICÇÃO",
    "fechamento": "MECÂNICA VIROU MITO",
    "contexto": "",
}


def gerar_cenas(roteiro: str, tema: str) -> list[dict]:
    partes = _partes_narracao(roteiro, alvo=8)
    quantidade = max(7, min(10, len(partes)))
    partes = partes[:quantidade]
    duracao_por_cena = max(5, min(9, ceil(65 / max(quantidade, 1))))

    cenas = []
    inicio = 0
    total = len(partes)
    for idx, narracao in enumerate(partes, start=1):
        funcao = _funcao_por_indice(idx, total, narracao)
        palavras = _palavras_chave(narracao, tema)
        texto_tela = _texto_tela(idx, total, tema, funcao, narracao)
        cenas.append(
            {
                "id": idx,
                "inicio_estimado": inicio,
                "duracao": duracao_por_cena,
                "narracao": narracao,
                "texto_tela": texto_tela,
                "legenda_curta": _legenda_curta(narracao),
                "midia_necessaria": f"B-roll documental relacionado a {', '.join(palavras[:3])}",
                "palavras_chave": palavras,
                "palavras_chave_slug": _slug_palavras_chave(palavras),
                "funcao_narrativa_sugerida": funcao,
                "tipo_midia": "video" if funcao in {"gancho", "cultura_pop", "mito_vs_realidade", "contraste"} else "imagem",
                "status_midia": "pendente",
            }
        )
        inicio += duracao_por_cena
    return cenas


def gerar_cenas_projeto(pasta_projeto, tema: str | None = None) -> list[dict]:
    from pathlib import Path

    from src.utils import carregar_json, atualizar_status

    pasta = Path(pasta_projeto)
    tema_final = tema or (pasta / "tema.txt").read_text(encoding="utf-8").strip()
    roteiro_path = pasta / "roteiro" / "roteiro_narrado.txt"
    if not roteiro_path.exists():
        roteiro_path = pasta / "roteiro.txt"
    roteiro = roteiro_path.read_text(encoding="utf-8").strip()
    cenas = gerar_cenas(roteiro, tema_final)
    (pasta / "cenas.json").write_text(
        carregar_json.dumps(cenas, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    atualizar_status(pasta, cenas="concluido")
    print("Cenas criadas")
    return cenas


def _partes_narracao(roteiro: str, alvo: int) -> list[str]:
    frases = [normalizar_texto_portugues(f) for f in re.split(r"(?<=[.!?])\s+", roteiro) if f.strip()]
    if not frases:
        return []
    grupos: list[str] = []
    atual: list[str] = []
    for frase in frases:
        atual.append(frase)
        palavras = len(" ".join(atual).split())
        if len(atual) >= 2 or palavras >= 24:
            grupos.append(" ".join(atual))
            atual = []
    if atual:
        if grupos and len(" ".join(atual).split()) < 10:
            grupos[-1] = f"{grupos[-1]} {' '.join(atual)}"
        else:
            grupos.append(" ".join(atual))

    if len(grupos) < 7 and len(frases) <= 10:
        grupos = frases
    if len(grupos) > 10:
        grupos = _compactar_grupos(grupos, alvo=alvo)
    return [p if p.endswith((".", "!", "?")) else p + "." for p in grupos if p]


def _compactar_grupos(grupos: list[str], alvo: int) -> list[str]:
    resultado = []
    atual = ""
    for grupo in grupos:
        tentativa = f"{atual} {grupo}".strip()
        if atual and (len(resultado) + 1 < alvo) and len(tentativa.split()) <= 34:
            atual = tentativa
        else:
            if atual:
                resultado.append(atual)
            atual = grupo
    if atual:
        resultado.append(atual)
    return resultado


def _funcao_por_indice(idx: int, total: int, narracao: str) -> str:
    texto = narracao.lower()
    if idx == 1:
        return "gancho"
    if idx == total:
        return "fechamento"
    if any(t in texto for t in ["cinema", "hollywood", "tela", "cultura"]):
        return "cultura_pop"
    if any(t in texto for t in ["potência", "peso", "recuo", "controle", "engenharia"]):
        return "explicacao"
    if any(t in texto for t in ["ficção", "realidade", "mito", "limites"]):
        return "contraste"
    return "contexto"


def _palavras_chave(texto: str, tema: str) -> list[str]:
    termos = []
    for parte in [tema, texto]:
        for raw in re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", parte.lower()):
            termo = normalizar_texto_portugues(raw)
            if termo and termo not in STOPWORDS and termo not in termos:
                termos.append(termo)
    return termos[:10] or ["curiosidade", "documentario", "fatos"]


def _texto_tela(idx: int, total: int, tema: str, funcao: str, narracao: str) -> str:
    if funcao == "gancho":
        return _titulo_curto_tema(tema).upper()
    if funcao == "cultura_pop" and idx > 3:
        return ""
    if funcao in {"explicacao", "contexto"} and idx not in {3, total - 1}:
        return ""
    texto = TEXTOS_VISUAIS.get(funcao, "")
    if texto:
        return texto
    if idx == total:
        return "MECÂNICA VIROU MITO"
    return ""


def _legenda_curta(texto: str) -> str:
    return " ".join(texto.split())


def _titulo_curto_tema(tema: str) -> str:
    palavras = " ".join(tema.split()).split()
    return " ".join(palavras[:6])


def _slug_palavras_chave(palavras: list[str]) -> list[str]:
    return [criar_slug(palavra) for palavra in palavras]
