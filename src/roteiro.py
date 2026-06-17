from __future__ import annotations


def gerar_roteiro(tema: str) -> str:
    tema_limpo = tema.strip()
    return (
        f"Voce provavelmente ja ouviu falar sobre {tema_limpo} como se fosse algo simples, "
        f"mas a historia real costuma ser bem mais interessante. Em poucos segundos, da para "
        f"perceber que {tema_limpo} mistura fama, exagero e detalhes que quase nunca aparecem "
        f"nas conversas comuns. O primeiro ponto e entender o contexto: muita coisa que parece "
        f"obvia nasceu de filmes, manchetes, comparacoes populares ou repeticao na internet. "
        f"Na pratica, o tema fica mais curioso quando olhamos para o que ele realmente significa, "
        f"para os limites que existem e para a diferenca entre mito e realidade. E e exatamente "
        f"ai que {tema_limpo} chama atencao: nao apenas pelo impacto inicial, mas porque mostra "
        f"como uma ideia pode virar lenda quando encontra cultura popular, memoria coletiva e "
        f"um pouco de surpresa. No fim, a verdade pode ser menos cinematografica, mas quase "
        f"sempre e mais fascinante."
    )
