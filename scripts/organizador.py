#!/usr/bin/env python3
import os
import shutil
import subprocess
import json
import requests

BASE_DIR = os.path.expanduser("~/homelab/organizador")
INBOX_DIR = os.path.join(BASE_DIR, "inbox")
ORGANIZADOS_DIR = os.path.join(BASE_DIR, "organizados")
QUARENTENA_DIR = os.path.join(BASE_DIR, "quarentena_sem_tags")
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Categorias voltadas para referências artísticas
CATEGORIAS_ARTISTICAS = {
    "nsfw": "Conteúdo adulto, nudez, anatomia explícita, referências sensíveis (+18)",
    "esboco": "Esboços, sketches, estudos de pose, gestual, anatomia básica, rascunhos rápidos, thumbnails",
    "perspectiva": "Pontos de fuga, grids de perspectiva, arquitetura, enquadramento de câmera, composição espacial",
    "ambientacao": "Cenários, backgrounds, iluminação, paletas de cores, atmosfera, paisagens, moodboards, concept art de ambiente",
    "lineart": "Traço limpo, inking, hachuras, estilos de contorno, arte vetorial, finalização de linhas"
}

def gerar_caminho_seguro(pasta_destino, nome_arquivo):
    """Garante que nunca sobrescreva um arquivo existente, adicionando sufixo incremental."""
    caminho_final = os.path.join(pasta_destino, nome_arquivo)
    if not os.path.exists(caminho_final):
        return caminho_final

    nome_base, extensao = os.path.splitext(nome_arquivo)
    contador = 1
    while True:
        novo_nome = f"{nome_base}_{contador}{extensao}"
        caminho_final = os.path.join(pasta_destino, novo_nome)
        if not os.path.exists(caminho_final):
            return caminho_final
        contador += 1

def extrair_metadados(caminho_arquivo):
    """Extrai tags IPTC, XMP e EXIF (Keywords, Subject, Tags, Description, Comment)."""
    try:
        cmd = [
            "exiftool", "-j",
            "-Keywords", "-Subject", "-TagsList", "-XPKeywords",
            "-Description", "-Comment", "-UserComment",
            caminho_arquivo
        ]
        resultado = subprocess.run(cmd, capture_output=True, text=True, check=True)
        dados = json.loads(resultado.stdout)
        if dados and isinstance(dados, list):
            metadados_uteis = {k: v for k, v in dados[0].items() if k != "SourceFile" and v}
            return metadados_uteis
    except Exception as e:
        print(f"[!] Erro ao ler metadados de {os.path.basename(caminho_arquivo)}: {e}")
    return {}

def classificar_com_ia(nome_arquivo, metadados):
    """Envia as tags para o Ollama decidir a categoria artística mais coerente."""
    prompt = f"""
Você é um curador e organizador de biblioteca de referências para ilustradores e artistas.
Analise as tags e metadados de uma imagem de referência artística para decidir em qual subpasta técnica ela deve ficar.

Arquivo: {nome_arquivo}
Metadados/Tags encontrados: {json.dumps(metadados, ensure_ascii=False)}

Categorias permitidas e seus critérios:
{json.dumps(CATEGORIAS_ARTISTICAS, indent=2, ensure_ascii=False)}

Regras estritas:
1. Prioridade máxima: se houver indicação de conteúdo adulto/nudez nas tags, classifique como "nsfw".
2. Escolha estritamente UMA das opções: {list(CATEGORIAS_ARTISTICAS.keys())}.
3. Mantenha o nome original ou sugira um nome limpo em letras minúsculas separado por hifens, preservando a extensão original.
4. Responda EXCLUSIVAMENTE em formato JSON puro, sem comentários.

Exemplo de saída:
{{"subpasta": "perspectiva", "novo_nome": "grid-cidade-3-pontos.jpg"}}
"""
    payload = {
        "model": "qwen2.5:1.5b",
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1}
    }

    try:
        resposta = requests.post(OLLAMA_URL, json=payload, timeout=30)
        if resposta.status_code == 200:
            corpo = json.loads(resposta.json().get("response", "{}"))
            if "subpasta" in corpo and corpo["subpasta"] in CATEGORIAS_ARTISTICAS:
                return corpo
    except Exception as e:
        print(f"[!] Erro ao consultar o Ollama: {e}")
    return None

def processar_triagem():
    arquivos = [f for f in os.listdir(INBOX_DIR) if os.path.isfile(os.path.join(INBOX_DIR, f))]
    
    if not arquivos:
        print("[i] Pasta 'inbox' vazia. Nada a processar.")
        return

    print(f"[*] Iniciando organização artística de {len(arquivos)} imagem(ns)...")

    for arquivo in arquivos:
        origem = os.path.join(INBOX_DIR, arquivo)
        metadados = extrair_metadados(origem)

        # Se não houver tags, vai intacto para a quarentena
        if not metadados:
            print(f"[?] Sem tags de referência: {arquivo} -> Quarentena")
            destino = gerar_caminho_seguro(QUARENTENA_DIR, arquivo)
            shutil.move(origem, destino)
            continue

        # Avaliação semântica via Qwen
        decisao = classificar_com_ia(arquivo, metadados)

        if decisao:
            subpasta = decisao["subpasta"]
            novo_nome = decisao.get("novo_nome", arquivo)
            pasta_destino = os.path.join(ORGANIZADOS_DIR, subpasta)
            os.makedirs(pasta_destino, exist_ok=True)

            destino_final = gerar_caminho_seguro(pasta_destino, novo_nome)
            shutil.move(origem, destino_final)
            print(f"[✓] Classificado: {arquivo} -> {subpasta}/{os.path.basename(destino_final)}")
        else:
            # Qualquer incerteza mantém o arquivo seguro na quarentena
            print(f"[!] Dúvida/Falha de triagem: {arquivo} -> Quarentena")
            destino = gerar_caminho_seguro(QUARENTENA_DIR, arquivo)
            shutil.move(origem, destino)

if __name__ == "__main__":
    processar_triagem()
