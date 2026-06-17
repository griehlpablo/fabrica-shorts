from __future__ import annotations

from pathlib import Path

from src.utils import carregar_json_arquivo, criar_slug, normalizar_texto_portugues, salvar_json


REGRAS_INTENCAO = [
    {
        "nome": "cultura_pop",
        "gatilhos": ["cinema", "hollywood", "filme", "tela", "lenda", "cultura pop", "histórias policiais"],
        "funcao_narrativa": "cultura_pop",
        "emocao": "curiosidade",
        "tipos": ["video_curto", "broll", "cinema", "close"],
        "pt": ["cinema", "Hollywood", "cultura pop", "revólver close documental"],
        "en": ["movie theater", "cinema projector", "action movie", "revolver close up"],
        "evitar": ["meme", "clickbait", "gore", "violence"],
        "prioridade": 8,
    },
    {
        "nome": "potencia_mito",
        "gatilhos": ["potência", "impacto", "força", "imparável", "som"],
        "funcao_narrativa": "mito_vs_realidade",
        "emocao": "impacto",
        "tipos": ["video_curto", "broll", "close", "demonstracao_controlada"],
        "pt": ["potência", "teste balístico controlado", "objeto inerte", "close documental"],
        "en": ["44 magnum", "revolver recoil", "ballistic test", "muzzle flash", "revolver close up"],
        "evitar": ["gore", "injury", "tutorial", "how to shoot", "how to buy", "weapon training"],
        "prioridade": 9,
    },
    {
        "nome": "controle_recuo",
        "gatilhos": ["controle", "recuo", "peso", "mecânico", "mecânica"],
        "funcao_narrativa": "explicacao",
        "emocao": "documental",
        "tipos": ["video_curto", "close", "objeto", "demonstracao_controlada"],
        "pt": ["recuo revólver", "peso", "detalhe mecânico", "controle"],
        "en": ["revolver recoil", "handgun recoil", "slow motion recoil", "object detail"],
        "evitar": ["tutorial", "training", "tactical", "how to shoot"],
        "prioridade": 8,
    },
    {
        "nome": "contraste_realidade",
        "gatilhos": ["realidade", "fora da tela", "mito", "exagero", "exageros", "limites"],
        "funcao_narrativa": "contraste",
        "emocao": "contraste",
        "tipos": ["broll", "objeto", "fundo_abstrato", "textura"],
        "pt": ["mito contra realidade", "objeto real", "fundo documental"],
        "en": ["myth versus reality", "documentary background", "dark b roll", "real object"],
        "evitar": ["meme", "toy gun", "airsoft", "gore"],
        "prioridade": 7,
    },
    {
        "nome": "fechamento",
        "gatilhos": ["no fim", "mostra que", "verdade", "memória popular"],
        "funcao_narrativa": "fechamento",
        "emocao": "reflexão",
        "tipos": ["fundo_abstrato", "textura", "cinema", "broll"],
        "pt": ["fechamento documental", "cultura", "memória popular"],
        "en": ["documentary ending", "cinematic background", "archive texture"],
        "evitar": ["gore", "violence", "tutorial"],
        "prioridade": 6,
    },
]

DEFAULT_EVITAR = [
    "gore",
    "ferimentos",
    "violência",
    "violence",
    "tutorial",
    "how to",
    "how to buy",
    "how to modify",
    "tactical",
    "extremist",
    "airsoft",
    "toy gun",
]


def gerar_plano_visual(pasta_projeto: Path) -> list[dict]:
    cenas = carregar_json_arquivo(pasta_projeto / "cenas.json", default=[])
    tema = _ler_texto(pasta_projeto / "tema.txt")
    roteiro = _ler_texto(pasta_projeto / "roteiro" / "roteiro_narrado.txt") or _ler_texto(pasta_projeto / "roteiro.txt")
    plano = []

    for indice, cena in enumerate(cenas, start=1):
        item = _classificar_cena(cena, tema, roteiro, indice, len(cenas))
        plano.append(item)

    salvar_json(pasta_projeto / "plano_visual.json", plano)
    _salvar_shotlist(pasta_projeto, plano)
    print(f"Plano visual gerado: {pasta_projeto / 'plano_visual.json'}")
    print(f"Shotlist gerado: {pasta_projeto / 'shotlist.md'}")
    return plano


def _classificar_cena(cena: dict, tema: str, roteiro: str, indice: int, total: int) -> dict:
    texto_narrado = normalizar_texto_portugues(str(cena.get("narracao", "")))
    texto_tela = _texto_tela_curto(str(cena.get("texto_tela") or "Curiosidade"))
    base = normalizar_texto_portugues(f"{tema} {texto_tela} {texto_narrado}").lower()
    melhor = None
    melhor_score = -1
    for regra in REGRAS_INTENCAO:
        score = sum(1 for gatilho in regra["gatilhos"] if gatilho.lower() in base)
        if score > melhor_score:
            melhor = regra
            melhor_score = score

    if melhor_score <= 0:
        melhor = _regra_default(indice, total)

    palavras_pt = _unicos([tema, *melhor["pt"], *cena.get("palavras_chave", [])])
    palavras_en = _unicos([*melhor["en"], *_termos_en_tema(tema)])
    evitar = _unicos([*DEFAULT_EVITAR, *melhor["evitar"]])
    return {
        "cena_id": cena["id"],
        "texto_narrado": texto_narrado,
        "texto_tela": texto_tela,
        "funcao_narrativa": melhor["funcao_narrativa"],
        "emocao": melhor["emocao"],
        "intencao_visual": _intencao_visual(melhor, tema),
        "tipo_de_midia_ideal": melhor["tipos"],
        "palavras_chave_pt": palavras_pt[:10],
        "palavras_chave_en": palavras_en[:10],
        "evitar": evitar,
        "prioridade_visual": int(melhor["prioridade"]),
    }


def _regra_default(indice: int, total: int) -> dict:
    if indice == 1:
        return {
            "funcao_narrativa": "gancho",
            "emocao": "impacto",
            "tipos": ["video_curto", "broll", "close"],
            "pt": ["gancho documental", "close dramático"],
            "en": ["cinematic close up", "documentary b roll"],
            "evitar": ["gore", "violence", "tutorial"],
            "prioridade": 8,
        }
    if indice == total:
        return REGRAS_INTENCAO[-1]
    return {
        "funcao_narrativa": "contexto",
        "emocao": "documental",
        "tipos": ["broll", "imagem", "textura", "fundo_abstrato"],
        "pt": ["contexto documental", "fundo cinematográfico"],
        "en": ["documentary background", "cinematic texture", "archive b roll"],
        "evitar": ["gore", "violence", "tutorial"],
        "prioridade": 5,
    }


def _intencao_visual(regra: dict, tema: str) -> str:
    if "magnum" in tema.lower() or ".44" in tema:
        return "mostrar o tema como objeto cultural e documental, sem instrução de uso ou glorificação de violência"
    return f"mostrar {tema} com linguagem documental, clara e visualmente variada"


def _texto_tela_curto(texto: str) -> str:
    palavras = normalizar_texto_portugues(texto).split()
    return " ".join(palavras[:6])


def _termos_en_tema(tema: str) -> list[str]:
    texto = criar_slug(tema).replace("_", " ")
    extras = [texto] if texto else []
    if "44" in texto or "magnum" in texto:
        extras.extend(["44 magnum", "revolver documentary", "revolver close up"])
    return extras


def _salvar_shotlist(pasta_projeto: Path, plano: list[dict]) -> None:
    linhas = ["# Shotlist", ""]
    for item in plano:
        linhas.extend(
            [
                f"## Cena {item['cena_id']}",
                f"- texto_tela: {item['texto_tela']}",
                f"- função narrativa: {item['funcao_narrativa']}",
                f"- intenção visual: {item['intencao_visual']}",
                f"- mídia ideal: {', '.join(item['tipo_de_midia_ideal'])}",
                f"- palavras-chave PT: {', '.join(item['palavras_chave_pt'])}",
                f"- palavras-chave EN: {', '.join(item['palavras_chave_en'])}",
                f"- evitar: {', '.join(item['evitar'])}",
                f"- prioridade: {item['prioridade_visual']}",
                "",
            ]
        )
    (pasta_projeto / "shotlist.md").write_text("\n".join(linhas), encoding="utf-8")


def _ler_texto(path: Path) -> str:
    if not path.exists():
        return ""
    return normalizar_texto_portugues(path.read_text(encoding="utf-8", errors="replace"))


def _unicos(valores: list[str]) -> list[str]:
    resultado = []
    for valor in valores:
        valor = normalizar_texto_portugues(str(valor))
        if valor and valor.lower() not in [x.lower() for x in resultado]:
            resultado.append(valor)
    return resultado
