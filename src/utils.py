from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


class carregar_json:
    dumps = staticmethod(json.dumps)


PROJECT_SUBDIRS = [
    "pesquisa",
    "roteiro",
    "midias/aprovadas",
    "midias/revisar",
    "midias/precisa_autorizacao",
    "midias/rejeitadas",
    "links_sugeridos",
    "licencas",
    "audio",
    "legendas",
    "render",
    "pacote_postagem",
    "logs",
]

PROJECT_STEPS = [
    "pesquisa",
    "roteiro",
    "cenas",
    "midias",
    "narracao",
    "legendas",
    "montagem",
    "pacote",
]


def criar_slug(texto: str) -> str:
    normalized = unicodedata.normalize("NFKD", texto)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_").lower()
    return ascii_text or "projeto_sem_titulo"


def slugify(texto: str) -> str:
    return criar_slug(texto)


def normalizar_texto_portugues(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto or "")
    return re.sub(r"\s+", " ", texto).strip()


def sanitizar_nome_arquivo(texto: str) -> str:
    texto = normalizar_texto_portugues(texto)
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" .")
    return texto or "arquivo"


def ambiente_utf8() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def projeto_path(base_dir: Path, nome: str) -> Path:
    pasta = base_dir / "projetos" / nome
    if not pasta.exists():
        raise FileNotFoundError(pasta)
    return pasta


def criar_estrutura_projeto(base_dir: Path, nome: str, nicho: str, tema: str) -> Path:
    pasta = base_dir / "projetos" / nome
    pasta.mkdir(parents=True, exist_ok=True)
    for subdir in PROJECT_SUBDIRS:
        (pasta / subdir).mkdir(parents=True, exist_ok=True)

    escrever_se_nao_existir(pasta / "tema.txt", tema + "\n")
    escrever_se_nao_existir(pasta / "midias" / "imagens.txt", "")
    escrever_se_nao_existir(pasta / "midias" / "videos.txt", "")
    escrever_se_nao_existir(pasta / "midias" / "referencias.txt", "")
    escrever_se_nao_existir(pasta / "links_sugeridos" / "imagens.txt", "")
    escrever_se_nao_existir(pasta / "links_sugeridos" / "videos.txt", "")
    escrever_se_nao_existir(pasta / "links_sugeridos" / "referencias.txt", "")

    status_path = pasta / "status.json"
    if not status_path.exists():
        salvar_json(
            status_path,
            {
                "projeto": nome,
                "nicho": nicho,
                "status": "criado",
                "etapas": {etapa: "pendente" for etapa in PROJECT_STEPS},
            },
        )
    else:
        dados = carregar_json_arquivo(status_path)
        etapas = dados.setdefault("etapas", {})
        alterado = False
        for etapa in PROJECT_STEPS:
            if etapa not in etapas:
                etapas[etapa] = "pendente"
                alterado = True
        if alterado:
            salvar_json(status_path, dados)
    return pasta


def escrever_se_nao_existir(path: Path, conteudo: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(conteudo, encoding="utf-8")


def carregar_json_arquivo(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def salvar_json(path: Path, dados: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def atualizar_status(pasta_projeto: Path, status: str | None = None, **etapas: str) -> None:
    status_path = pasta_projeto / "status.json"
    dados = carregar_json_arquivo(status_path)
    if status:
        dados["status"] = status
    dados.setdefault("etapas", {})
    for etapa, valor in etapas.items():
        dados["etapas"][etapa] = valor
    salvar_json(status_path, dados)


def copiar_arquivo(origem: Path, destino_dir: Path) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / origem.name
    if destino.exists():
        stem = destino.stem
        suffix = destino.suffix
        destino = destino_dir / f"{stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
    shutil.copy2(origem, destino)
    return destino


def ffmpeg_disponivel() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_disponivel() -> bool:
    return shutil.which("ffprobe") is not None


def obter_duracao_midia(caminho: Path) -> float | None:
    if not ffprobe_disponivel() or not caminho.exists():
        return None
    resultado = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(caminho),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        env=ambiente_utf8(),
        timeout=30,
    )
    if resultado.returncode != 0:
        return None
    try:
        return float(resultado.stdout.strip())
    except ValueError:
        return None


def obter_duracao_midias(caminho: Path) -> float | None:
    return obter_duracao_midia(caminho)


def executar(
    cmd: list[str],
    log_path: Path | None = None,
    etapa: str | None = None,
    cena_id: int | str | None = None,
    timeout: int = 120,
) -> None:
    try:
        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=ambiente_utf8(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partes = [
            "Etapa:",
            etapa or "nao informada",
            "",
            "Cena:",
            str(cena_id) if cena_id is not None else "nao informada",
            "",
            "Timeout:",
            f"Comando excedeu {timeout} segundos e foi interrompido.",
            "",
            "Comando executado:",
            " ".join(cmd),
            "",
            "STDOUT parcial:",
            _normalizar_saida_subprocess(exc.stdout),
            "",
            "STDERR parcial:",
            _normalizar_saida_subprocess(exc.stderr),
        ]
        mensagem = "\n".join(partes).strip()
        _salvar_log_execucao(log_path, mensagem)
        raise RuntimeError(f"Timeout ao executar FFmpeg apos {timeout} segundos. Veja logs/montagem_erro.txt.") from exc

    if resultado.returncode != 0:
        partes = [
            "Etapa:",
            etapa or "nao informada",
            "",
            "Cena:",
            str(cena_id) if cena_id is not None else "nao informada",
            "",
            "Comando executado:",
            " ".join(cmd),
            "",
            "STDOUT:",
            resultado.stdout.strip(),
            "",
            "STDERR:",
            resultado.stderr.strip(),
        ]
        mensagem = "\n".join(partes).strip()
        _salvar_log_execucao(log_path, mensagem)
        raise RuntimeError(mensagem)


def _normalizar_saida_subprocess(saida: str | bytes | None) -> str:
    if saida is None:
        return ""
    if isinstance(saida, bytes):
        return saida.decode("utf-8", errors="replace").strip()
    return saida.strip()


def _salvar_log_execucao(log_path: Path | None, mensagem: str) -> None:
    if not log_path:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(mensagem, encoding="utf-8")
    if log_path.parent.name == "logs":
        (log_path.parent / "montagem_erro.txt").write_text(mensagem, encoding="utf-8")
