# fabrica-shorts

Fabrica local de videos curtos verticais para YouTube Shorts, TikTok, Kwai, Instagram Reels e Facebook Reels.

Esta primeira versao e um MVP focado no nicho `curiosidade`. Ela nao usa API paga, nao baixa videos automaticamente, nao faz upload para plataformas e nao exige Ollama, Whisper ou TTS.

## O que o MVP faz

- Cria uma pasta de projeto em `projetos/`.
- Gera um roteiro simples por template local.
- Divide o roteiro em cenas e salva `cenas.json`.
- Procura midias locais em `biblioteca/`.
- Copia midias encontradas para `midias/aprovadas/`.
- Monta um video vertical 1080x1920 com FFmpeg.
- Gera legenda `.srt`.
- Cria um pacote de postagem com titulo, descricao, hashtags e checklist.

## Requisitos

- Python 3.10 ou superior.
- FFmpeg instalado e disponivel no `PATH`.

No Windows, baixe o FFmpeg em um site confiavel, extraia a pasta e adicione a pasta `bin` ao `PATH`. Depois confirme no terminal:

```powershell
ffmpeg -version
```

## Instalar dependencias

O MVP usa apenas a biblioteca padrao do Python, entao nao ha pacotes obrigatorios:

```powershell
pip install -r requirements.txt
```

## Criar um projeto

```powershell
python main.py criar --nicho curiosidade --tema "O poder real da .44 Magnum"
```

Isso cria uma pasta como:

```text
projetos/o_poder_real_da_44_magnum/
```

com `tema.txt`, `roteiro.txt`, `cenas.json`, `plano_midias.json`, `status.json` e as subpastas de midia, legenda, render, logs e pacote.

## Adicionar midias na biblioteca

Coloque imagens e videos proprios, licenciados ou aprovados manualmente nestas pastas:

```text
biblioteca/imagens/
biblioteca/videos/
biblioteca/fundos/
biblioteca/sons/
biblioteca/musicas/
```

Use nomes descritivos. Exemplo:

```text
magnum_44.mp4
revolver_close.jpg
historia_cinema.mp4
```

O sistema procura arquivos cujo nome combine com palavras-chave das cenas.

## Verificar midias

```powershell
python main.py midias --projeto o_poder_real_da_44_magnum
```

Se nao encontrar midia local, o projeto continua funcionando e o montador usa fundo temporario com texto.

## Montar video

```powershell
python main.py montar --projeto o_poder_real_da_44_magnum
```

O video final fica em:

```text
projetos/o_poder_real_da_44_magnum/pacote_postagem/video_final.mp4
```

Se o FFmpeg nao estiver instalado, o sistema mostra:

```text
FFmpeg nao encontrado. Instale o FFmpeg e adicione ao PATH.
```

## Gerar pacote

```powershell
python main.py pacote --projeto o_poder_real_da_44_magnum
```

Arquivos gerados:

```text
pacote_postagem/video_final.mp4
pacote_postagem/legenda.srt
pacote_postagem/titulo.txt
pacote_postagem/descricao.txt
pacote_postagem/hashtags.txt
pacote_postagem/checklist_publicacao.txt
```

## Rodar tudo

```powershell
python main.py tudo --nicho curiosidade --tema "O poder real da .44 Magnum"
```

## O que ainda e manual

- Revisar direitos autorais das midias.
- Inserir links e licencas manualmente quando necessario.
- Postar manualmente em cada plataforma.
- Revisar titulo, descricao, hashtags e legenda antes da publicacao.
- Substituir fundos temporarios por midias melhores quando desejar.

## Cuidados com direitos autorais e monetizacao

Este MVP nunca baixa automaticamente midias de YouTube, TikTok, Instagram, Reddit, filmes, series, transmissoes esportivas, podcasts ou canais de terceiros.

Use preferencialmente:

- midias proprias;
- midias licenciadas;
- bancos gratuitos com licenca clara;
- conteudo autorizado por escrito.

Midias de filmes, series, transmissoes esportivas, podcasts, musicas comerciais e canais de terceiros devem ser tratadas como `PRECISA_AUTORIZACAO`.

## Subir futuramente para GitHub

Quando quiser versionar:

```powershell
git init
git add .
git commit -m "Cria MVP da fabrica de shorts"
```

Depois crie um repositorio no GitHub e siga as instrucoes exibidas por ele para adicionar o remoto e enviar o projeto.

## Rodar em outra maquina

Em um notebook antigo ou maquina dedicada:

1. Instale Python.
2. Instale FFmpeg e adicione ao `PATH`.
3. Copie ou clone o projeto.
4. Coloque midias aprovadas em `biblioteca/`.
5. Rode os comandos pelo terminal.

O projeto foi pensado para uso leve: sem IA local pesada, sem interface grafica obrigatoria e sem processamento paralelo por padrao.
