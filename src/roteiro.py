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
                "gancho",
                "contexto rapido",
                "desenvolvimento",
                "virada",
                "fechamento",
            ],
            "tom": "curiosidade documental",
            "seguranca": "educativo, cultural e nao instrucional",
        },
    )
    atualizar_status(pasta_projeto, roteiro="concluido")
    print("Roteiro criado")
    return roteiro


def _roteiro_curiosidade_padrao(tema: str) -> str:
    return (
        f"{tema} parece uma curiosidade pequena, ate voce perceber que ela virou historia. "
        "Primeiro vem a imagem: uma frase repetida, uma cena marcante, uma comparacao facil de lembrar. "
        "Depois vem o contexto, porque quase todo mito nasce de um detalhe real que foi aumentado pelo tempo. "
        "A virada aparece quando a fama encontra a realidade. "
        "O que parecia simples ganha limites, personagens, duvidas e exageros. "
        "E e ai que o assunto fica interessante: nao pelo impacto inicial, mas pelo caminho que transformou um fato em memoria popular. "
        f"No fim, {tema} mostra que algumas lendas nao nascem de uma mentira. Nascem de uma verdade contada vezes demais."
    )


def _roteiro_arma_cultural(tema: str) -> str:
    return (
        "Ela virou simbolo de forca no cinema. "
        f"Mas a fama de {tema} nao nasceu so da potencia. Nasceu da imagem. Do som. Da forma como Hollywood transformou um objeto mecanico em lenda. "
        "Durante anos, filmes e historias policiais venderam a ideia de algo quase imparavel. "
        "So que fora da tela, a conversa muda. "
        "Potencia nao significa controle, e controle importa muito mais do que a cena costuma mostrar. "
        "Peso, recuo e contexto fazem a realidade parecer menos cinematografica, mas muito mais interessante. "
        f"No fim, {tema} e menos sobre ser imparavel, e mais sobre como o cinema transforma mecanica em mito."
    )


def _tema_sensivel_armas(tema: str) -> bool:
    texto = tema.lower()
    termos = ["arma", "revolver", "pistola", "magnum", "calibre", ".44", "44"]
    return any(termo in texto for termo in termos)
