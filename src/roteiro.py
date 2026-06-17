from __future__ import annotations

from pathlib import Path

from src.utils import atualizar_status, salvar_json


def gerar_roteiro(tema: str) -> str:
    tema_limpo = tema.strip()
    if _tema_sensivel_armas(tema_limpo):
        return _roteiro_arma_cultural(tema_limpo)
    return _roteiro_curiosidade_padrao(tema_limpo)


def gerar_roteiro_projeto(pasta_projeto: Path) -> str:
    tema = (pasta_projeto / "tema.txt").read_text(encoding="utf-8").strip()
    roteiro = gerar_roteiro(tema)
    roteiro_dir = pasta_projeto / "roteiro"
    roteiro_dir.mkdir(parents=True, exist_ok=True)
    (roteiro_dir / "roteiro_narrado.txt").write_text(roteiro + "\n", encoding="utf-8")
    (pasta_projeto / "roteiro.txt").write_text(roteiro + "\n", encoding="utf-8")
    salvar_json(
        roteiro_dir / "roteiro_visual.json",
        {
            "tema": tema,
            "estrutura": [
                "gancho forte",
                "contexto cultural",
                "mito",
                "realidade segura",
                "contraste",
                "fechamento memoravel",
            ],
            "tom": "mini-documentario cultural",
            "seguranca": "educativo, cultural e nao instrucional",
        },
    )
    atualizar_status(pasta_projeto, roteiro="concluido")
    print("Roteiro criado")
    return roteiro


def _roteiro_curiosidade_padrao(tema: str) -> str:
    return (
        f"{tema} parece uma curiosidade simples, mas quase toda curiosidade famosa esconde uma história maior. "
        "Primeiro existe uma imagem forte: uma cena repetida, um objeto marcante, uma frase que fica na memória. "
        "Depois vem o contexto, porque a cultura popular raramente cria um mito do nada; ela aumenta um detalhe real até ele parecer maior do que a própria realidade. "
        "É nesse ponto que a história fica interessante. A fama muda o modo como as pessoas enxergam o objeto, o personagem ou o acontecimento. "
        "O que era apenas um fato ganha atmosfera, exagero, comparação e até um pouco de mistério. "
        "Quando olhamos com calma, a diferença entre o símbolo e o mundo real revela mais sobre nós do que sobre o próprio tema. "
        f"No fim, {tema} mostra como uma lenda nasce quando realidade, memória e imaginação começam a contar a mesma história de jeitos diferentes."
    )


def _roteiro_arma_cultural(tema: str) -> str:
    return (
        f"{tema} virou símbolo cultural porque o cinema transformou um objeto mecânico em personagem. "
        "Na tela, ele aparece com presença, som e impacto visual, como se carregasse sozinho uma ideia de autoridade e exagero. "
        "Essa imagem ficou tão forte que muita gente conhece a lenda antes de conhecer o contexto. "
        "Mas fora da ficção, a história é menos simples e mais interessante. Potência também significa peso, recuo, volume e dificuldade de controle, ideias gerais que mudam completamente a leitura daquele mito. "
        "Por isso, a fama não vem apenas de números, metal ou engenharia. Vem da mistura entre design, cultura pop, histórias policiais e a linguagem dramática de Hollywood. "
        "O cinema pegou um objeto real e ampliou sua presença até ele parecer maior do que a vida cotidiana. "
        f"No fim, {tema} não é uma lição sobre uso ou poder prático. É um exemplo de como a cultura transforma mecânica em mito, e mito em memória visual."
    )


def _tema_sensivel_armas(tema: str) -> bool:
    texto = tema.lower()
    termos = ["arma", "revolver", "revólver", "pistola", "magnum", "calibre", ".44", "44"]
    return any(termo in texto for termo in termos)
