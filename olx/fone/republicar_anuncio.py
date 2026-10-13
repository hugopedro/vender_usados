#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script unificado para excluir e republicar automaticamente anúncios na OLX.
Suporta seleção de itens (Celular, Ventilador ou Fone) e verificação de cotas mensais.
Utiliza a sessão ativa e cookies do Firefox Nightly (sem necessidade de Playwright ou Selenium).
"""

import os
import sys
import glob
import shutil
import sqlite3
import uuid
import json
import time
import random
import argparse
import warnings
from datetime import datetime

# Configura codificação do console para UTF-8 no Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Suprime avisos cosméticos de versões de dependências do requests/urllib3
warnings.filterwarnings("ignore")

import cloudscraper

# Constantes e Endpoints da API OLX
TEAM_KEY_MYDATA = "5XzjuCgmYE7qMlYpsLZbTvm98ik4CS4a"
TEAM_KEY_UPLOAD = "YQfUIqhorSzk25LMoTrTzAQdECxourSd"

URL_LIST_ADS = "https://apigw.olx.com.br/mydata/v1/data?status=published&page=1&page_size=50&hv=1&eligibles=1"
URL_DELETE_AD = "https://auth-4ds.olx.com.br/bff/anuncio/"
URL_UPLOAD_IMAGE = "https://apigw.olx.com.br/ai/image"
URL_CREATE_AD = "https://apigw.olx.com.br/ai-bff/v2/anuncio/"

# Headers comuns simulando navegador real Firefox
BROWSER_HEADERS = {
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

# Nomes dos meses em português para exibição amigável
MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}


def human_delay(min_sec, max_sec, action_desc="", fast=False):
    """Pausa aleatória para simular o ritmo e tempo de reação de um usuário humano."""
    if fast:
        return
    duration = round(random.uniform(min_sec, max_sec), 2)
    if action_desc:
        print(f"  ⏳ {action_desc} (aguardando {duration}s)...")
    time.sleep(duration)


# Preferências padrão de pagamento e entrega (Garantia da OLX desativada)
ENABLE_OLX_PAY = False   # False = Desativa Garantia da OLX (apenas entrega em mãos)
ENABLE_OLX_SHIP = False  # False = Desativa envio/entrega pelos Correios

# Definição dos itens suportados e seus limites oficiais de cotas gratuitas
ITENS_CONFIG = {
    "celular": {
        "nome": "Celular Smartphone Samsung Galaxy S23",
        "categoria_nome": "Celulares e telefonia",
        "pasta": "celular",
        "keywords": ["galaxy", "s23", "samsung", "celular", "smartphone"],
        "category_id": 3060,
        "limite_mensal": 5,
    },
    "ventilador": {
        "nome": "Ventilador Mondial Torre Semi Novo",
        "categoria_nome": "Eletrodomésticos",
        "pasta": "ventilador",
        "keywords": ["ventilador", "mondial", "torre"],
        "category_id": 20020,
        "limite_mensal": 20,
    },
    "fone": {
        "nome": "Headset Headphone Fone JBL Quantum 400",
        "categoria_nome": "Áudio, fones e caixas de som",
        "pasta": "fone",
        "keywords": ["jbl", "headset", "fone", "headphone", "quantum"],
        "category_id": 18020,
        "limite_mensal": 20,
    },
    "memoria": {
        "nome": "Memória RAM 8GB DDR4",
        "categoria_nome": "Informática e peças de PC",
        "pasta": "memoria",
        "keywords": ["memória", "memoria", "ram", "ddr4", "kingston", "8gb"],
        "category_id": 19080,
        "limite_mensal": 20,
    }
}


def find_olx_base_dir():
    """Identifica o diretório raiz do experimento OLX."""
    curr = os.path.abspath(os.getcwd())
    # Se está dentro de celular, ventilador, fone ou memoria, o root é o pai
    if os.path.basename(curr) in ("celular", "ventilador", "fone", "memoria"):
        return os.path.dirname(curr)
    # Se a pasta 'celular' existe aqui, este é o root
    if os.path.isdir(os.path.join(curr, "celular")):
        return curr
    # Fallback pelo caminho absoluto do script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(script_dir) in ("celular", "ventilador", "fone", "memoria"):
        return os.path.dirname(script_dir)
    return script_dir


# =====================================================================
# GERENCIAMENTO DE COTAS DE ANÚNCIOS GRATUITOS
# =====================================================================

def get_quota_file_path(base_dir):
    """Retorna o caminho do arquivo de histórico de cotas."""
    return os.path.join(base_dir, "historico_cotas.json")


def load_quota_history(base_dir):
    """Carrega o histórico de publicações do arquivo JSON."""
    file_path = get_quota_file_path(base_dir)
    if not os.path.exists(file_path):
        return {"publicacoes": []}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "publicacoes" in data:
                return data
    except Exception:
        pass
    return {"publicacoes": []}


def get_item_quota_status(base_dir, item_key):
    """Calcula o status atual da cota para o item no mês corrente."""
    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    mes_nome = f"{MESES_PT.get(now.month, str(now.month))}/{now.year}"

    cfg = ITENS_CONFIG[item_key]
    limite = cfg.get("limite_mensal", 20)

    history = load_quota_history(base_dir)
    item_pubs = [
        p for p in history.get("publicacoes", [])
        if p.get("item") == item_key and str(p.get("data", "")).startswith(month_prefix)
    ]

    usados = len(item_pubs)
    restantes = max(0, limite - usados)

    return {
        "item_key": item_key,
        "item_nome": cfg["nome"],
        "categoria_nome": cfg.get("categoria_nome", ""),
        "mes_nome": mes_nome,
        "limite": limite,
        "usados": usados,
        "restantes": restantes,
        "publicacoes_mes": item_pubs
    }


def record_quota_publication(base_dir, item_key, ad_id, list_id, title):
    """Registra uma nova publicação no histórico de cotas."""
    file_path = get_quota_file_path(base_dir)
    history = load_quota_history(base_dir)
    nova_pub = {
        "item": item_key,
        "ad_id": int(ad_id) if (ad_id and str(ad_id).isdigit()) else ad_id,
        "list_id": str(list_id) if list_id else "",
        "titulo": title or ITENS_CONFIG[item_key]["nome"],
        "data": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }
    history["publicacoes"].append(nova_pub)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  [!] Aviso: Não foi possível salvar o registro de cota: {e}")


def format_iso_datetime(dt_str):
    """Formata timestamp ISO (YYYY-MM-DDTHH:MM:SS) para DD/MM/AAAA às HH:MM."""
    if not dt_str:
        return ""
    try:
        parts = dt_str.split("T")
        d_parts = parts[0].split("-")
        time_part = parts[1][:5] if len(parts) > 1 else ""
        return f"{d_parts[2]}/{d_parts[1]}/{d_parts[0]} às {time_part}"
    except Exception:
        return dt_str


def display_quota_report(base_dir):
    """Exibe um relatório detalhado das cotas gratuitas mensais de todos os itens."""
    now = datetime.now()
    mes_nome = f"{MESES_PT.get(now.month, str(now.month))}/{now.year}"

    print("=" * 68)
    print(f"       RELATÓRIO DE COTAS DE ANÚNCIOS GRATUITOS - {mes_nome.upper()}")
    print("=" * 68)
    print("ℹ️  A OLX renova o limite de inserções gratuitas mensalmente.")
    print("-" * 68)

    for idx, (item_key, cfg) in enumerate(ITENS_CONFIG.items(), start=1):
        status = get_item_quota_status(base_dir, item_key)
        limite = status["limite"]
        usados = status["usados"]
        restantes = status["restantes"]

        print(f"\n[{idx}] {cfg['nome']}")
        print(f"    • Categoria:       {cfg.get('categoria_nome', 'Geral')}")
        print(f"    • Limite mensal:   {limite} anúncios gratuitos")
        print(f"    • Utilizados:      {usados} anúncio(s) em {mes_nome}")
        if restantes > 0:
            print(f"    • Saldo restante:  ✓ Você tem direito a mais {restantes} anúncio(s) gratuito(s)!")
        else:
            print(f"    • Saldo restante:  ⚠️ Limite gratuito atingido (0 restantes este mês).")

        pubs = status["publicacoes_mes"]
        if pubs:
            print(f"    • Histórico deste mês ({len(pubs)}):")
            for p in pubs:
                d_fmt = format_iso_datetime(p.get("data", ""))
                p_id = p.get("ad_id", "N/A")
                print(f"      - {d_fmt} | Ad ID: {p_id}")

    print("\n" + "=" * 68)


# =====================================================================
# OPERAÇÕES DE NAVEGAÇÃO E API OLX
# =====================================================================

def find_firefox_profile():
    """Localiza o diretório do perfil ativo do Firefox Nightly."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("Variável de ambiente APPDATA não encontrada.")

    profiles_dir = os.path.join(appdata, "Mozilla", "Firefox", "Profiles")
    if not os.path.isdir(profiles_dir):
        raise RuntimeError(f"Diretório de perfis do Firefox não encontrado em: {profiles_dir}")

    # Prioriza perfil nightly, depois o mais recentemente modificado
    candidates = glob.glob(os.path.join(profiles_dir, "*nightly*"))
    if not candidates:
        candidates = glob.glob(os.path.join(profiles_dir, "*"))

    if not candidates:
        raise RuntimeError("Nenhum perfil do Firefox encontrado.")

    def get_cookie_mtime(p):
        c_path = os.path.join(p, "cookies.sqlite")
        return os.path.getmtime(c_path) if os.path.exists(c_path) else 0

    candidates.sort(key=get_cookie_mtime, reverse=True)
    return candidates[0]


def extract_olx_cookies(profile_path):
    """Extrai os cookies da OLX do banco SQLite do perfil do Firefox sem bloquear o navegador."""
    cookie_db = os.path.join(profile_path, "cookies.sqlite")
    if not os.path.exists(cookie_db):
        raise RuntimeError(f"Banco de cookies não encontrado em: {cookie_db}")

    temp_db = os.path.join(os.environ.get("TEMP", "."), f"temp_cookies_{uuid.uuid4().hex[:8]}.sqlite")
    temp_wal = temp_db + "-wal"

    try:
        shutil.copy2(cookie_db, temp_db)
        if os.path.exists(cookie_db + "-wal"):
            shutil.copy2(cookie_db + "-wal", temp_wal)

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name, value FROM moz_cookies WHERE host LIKE '%olx.com.br%'")
        cookies = dict(cursor.fetchall())
        conn.close()
        return cookies
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)
        if os.path.exists(temp_wal):
            os.remove(temp_wal)


def get_scraper():
    """Cria uma instância de scraper com fingerprint de navegador Firefox."""
    return cloudscraper.create_scraper(
        browser={
            "browser": "firefox",
            "platform": "windows",
            "mobile": False
        }
    )


def fetch_published_ads(scraper, cookies):
    """Busca a lista de anúncios publicados na conta."""
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://conta.olx.com.br/",
        "Origin": "https://conta.olx.com.br",
        "X-OLX-TEAM-KEY": TEAM_KEY_MYDATA
    }
    resp = scraper.get(URL_LIST_ADS, headers=headers, cookies=cookies, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Falha ao consultar anúncios publicados (HTTP {resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    return data.get("ads", [])


def match_ad(ads, item_key):
    """Identifica o anúncio correspondente ao item selecionado."""
    cfg = ITENS_CONFIG[item_key]
    cat_target = cfg["category_id"]
    keywords = cfg["keywords"]

    for ad in ads:
        subject = (ad.get("subject", "") or ad.get("title", "")).lower()
        cat = ad.get("category")
        if cat == cat_target or any(kw in subject for kw in keywords):
            return ad
    return None


def delete_ad(scraper, cookies, ad_id, list_id):
    """Exclui o anúncio atual via API oficial da OLX."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://conta.olx.com.br",
        "Referer": "https://conta.olx.com.br/anuncios/publicados",
        **BROWSER_HEADERS
    }
    payload = {
        "deletion_reason": "sold_by_others",
        "deletion_note": "",
        "ad_id": int(ad_id) if ad_id else 0,
        "list_id": str(list_id)
    }
    resp = scraper.delete(URL_DELETE_AD, headers=headers, cookies=cookies, json=payload, timeout=15)
    if resp.status_code in (200, 204):
        return True
    raise RuntimeError(f"Falha ao excluir anúncio (HTTP {resp.status_code}): {resp.text[:300]}")


def upload_images(scraper, cookies, item_dir, fast=False):
    """Faz upload das imagens locais da pasta do item e retorna os identificadores de mídia."""
    candidates = (
        glob.glob(os.path.join(item_dir, "*.jpg")) +
        glob.glob(os.path.join(item_dir, "*.png")) +
        glob.glob(os.path.join(item_dir, "imagens", "*.jpg")) +
        glob.glob(os.path.join(item_dir, "imagens", "*.png"))
    )
    seen = set()
    image_files = []
    for c in sorted(candidates):
        if c not in seen:
            seen.add(c)
            image_files.append(c)

    if not image_files:
        raise RuntimeError(f"Nenhuma imagem encontrada na pasta: {item_dir}")

    uploaded_names = []
    print(f"\n[+] Fazendo upload de {len(image_files)} imagens...")

    for idx, img_path in enumerate(image_files, start=1):
        filename = os.path.basename(img_path)
        req_id = str(uuid.uuid4())
        headers = {
            "Ai-Request-Id": req_id,
            "X-Request-Id": req_id,
            "X-OLX-TEAM-KEY": TEAM_KEY_UPLOAD,
            "Origin": "https://www2.olx.com.br",
            "Referer": "https://www2.olx.com.br/desapega",
            **BROWSER_HEADERS
        }
        with open(img_path, "rb") as f:
            files = {"file": (filename, f, "image/jpeg")}
            resp = scraper.post(URL_UPLOAD_IMAGE, headers=headers, cookies=cookies, files=files, timeout=20)

        if resp.status_code != 200:
            raise RuntimeError(f"Falha no upload da imagem {filename} (HTTP {resp.status_code}): {resp.text}")

        res_data = resp.json()
        uri = res_data.get("uri", "")
        media_name = uri.split("/")[-1]
        uploaded_names.append(media_name)
        print(f"  ✓ [{idx}/{len(image_files)}] {filename} -> {media_name}")

        # Pausa humanizada entre uploads de fotos
        if idx < len(image_files):
            human_delay(1.5, 3.2, "Simulando seleção da foto seguinte", fast=fast)

    return uploaded_names


def create_ad(scraper, cookies, base_ad, item_dir, uploaded_images, fast=False):
    """Publica o novo anúncio com os mesmos atributos técnicos e as novas fotos."""
    # Pausa humanizada simulando conferência do formulário
    human_delay(3.5, 6.5, "Simulando revisão dos dados antes de submeter", fast=fast)

    req_id = str(uuid.uuid4())
    idempotency_key = str(uuid.uuid4())
    test_ab = cookies.get("TestAB_Groups", "")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json, text/plain, */*",
        "Ai-Request-Id": req_id,
        "X-Request-Id": req_id,
        "X-Idempotency-Key": idempotency_key,
        "x-olxbr-testab-groups": test_ab,
        "Origin": "https://www2.olx.com.br",
        "Referer": "https://www2.olx.com.br/desapega",
        **BROWSER_HEADERS
    }

    # Carrega textos locais se disponíveis na pasta do item
    title_file = os.path.join(item_dir, "descricao_titulo.txt")
    body_file = os.path.join(item_dir, "descricao_corpo.txt")
    price_file = os.path.join(item_dir, "preco.txt")

    title = base_ad.get("subject", "")
    if os.path.exists(title_file):
        with open(title_file, "r", encoding="utf-8") as f:
            title = f.read().strip()

    body = base_ad.get("body", "")
    if os.path.exists(body_file):
        with open(body_file, "r", encoding="utf-8") as f:
            body = f.read().strip()

    price = base_ad.get("price", 0)
    if os.path.exists(price_file):
        with open(price_file, "r", encoding="utf-8") as f:
            p_str = f.read().strip()
            if p_str.isdigit():
                price = int(p_str)

    # Base payload
    payload = {
        "body": body,
        "category": base_ad.get("category"),
        "image": uploaded_images,
        "olx_pay": "1" if ENABLE_OLX_PAY else "0",
        "olx_ship": "1" if ENABLE_OLX_SHIP else "0",
        "phone": str(base_ad.get("phone", "13991192240")),
        "phone_hidden": bool(base_ad.get("phone_hidden", True)),
        "price": price,
        "source": "web",
        "subject": title,
        "type": "s",  # 's' = sell / vender
        "zipcode": str(base_ad.get("zipcode", "11040271")),
        "tokenAllowme": None
    }

    # Preserva automaticamente atributos específicos de categoria (celular, eletro, áudio, memória/info)
    for k, v in base_ad.items():
        if any(k.startswith(prefix) for prefix in ["eletro_", "cellphone_", "electronics_", "audio_", "info_"]):
            payload[k] = str(v)

    resp = scraper.post(URL_CREATE_AD, headers=headers, cookies=cookies, json=payload, timeout=20)
    if resp.status_code in (200, 201):
        res_data = resp.json()
        new_ad_id = res_data.get("ad_id") or res_data.get("adId")
        return new_ad_id, res_data
    raise RuntimeError(f"Falha ao criar novo anúncio (HTTP {resp.status_code}): {resp.text}")


def choose_item(item_arg):
    """Permite ao usuário escolher o item ou verificar cotas via CLI ou menu interativo."""
    if item_arg:
        key = item_arg.strip().lower()
        if key in ("1", "cel", "celular", "smartphone", "s23"):
            return "celular"
        if key in ("2", "vent", "ventilador", "torre", "mondial"):
            return "ventilador"
        if key in ("3", "fone", "headset", "headphone", "jbl", "quantum"):
            return "fone"
        if key in ("4", "mem", "memoria", "memória", "ram", "ddr4", "kingston"):
            return "memoria"
        if key in ("5", "cota", "cotas", "verificar", "saldo", "limite", "limites", "info"):
            return "cotas"
        print(f"[!] Opção '{item_arg}' não reconhecida. Escolha abaixo:")

    # Se executando de dentro da subpasta, detecta contexto
    cwd_name = os.path.basename(os.getcwd()).lower()
    default_choice = "1"
    if cwd_name == "celular":
        default_choice = "1"
    elif cwd_name == "ventilador":
        default_choice = "2"
    elif cwd_name == "fone":
        default_choice = "3"
    elif cwd_name == "memoria":
        default_choice = "4"

    print("\n[?] Qual ação você deseja realizar?")
    print("  1) Republicar Celular (Samsung Galaxy S23)")
    print("  2) Republicar Ventilador (Mondial Torre Semi Novo)")
    print("  3) Republicar Fone (Headset JBL Quantum 400)")
    print("  4) Republicar Memória RAM (Kingston 8GB DDR4)")
    print("  5) Verificar cotas de anúncios gratuitos")

    choice = input(f"\nEscolha a opção (1, 2, 3, 4 ou 5) [Padrão: {default_choice}]: ").strip()
    if not choice:
        choice = default_choice

    if choice in ("1", "celular"):
        return "celular"
    elif choice in ("2", "ventilador"):
        return "ventilador"
    elif choice in ("3", "fone"):
        return "fone"
    elif choice in ("4", "memoria", "memória", "ram"):
        return "memoria"
    elif choice in ("5", "cotas", "cota", "c"):
        return "cotas"
    else:
        print("Opção inválida. Selecionando Celular por padrão.")
        return "celular"


def main():
    parser = argparse.ArgumentParser(description="Excluir e republicar anúncio na OLX ou verificar cotas mensais")
    parser.add_argument("item", nargs="?", default=None, help="Item para republicar ('celular', 'ventilador', 'fone', 'memoria') ou 'cotas'")
    parser.add_argument("--item", "-i", dest="item_opt", default=None, help="Item para republicar: 'celular', 'ventilador', 'fone', 'memoria'")
    parser.add_argument("--cotas", "-c", action="store_true", help="Exibir saldo de cotas de anúncios gratuitos e sair")
    parser.add_argument("--yes", "-y", action="store_true", help="Executar sem pedir confirmação")
    parser.add_argument("--dry-run", action="store_true", help="Apenas inspecionar sem excluir ou criar nada")
    parser.add_argument("--fast", action="store_true", help="Desativar pausas humanizadas (modo rápido)")
    args = parser.parse_args()

    base_olx_dir = find_olx_base_dir()

    # Se a flag --cotas foi passada diretamente
    if args.cotas:
        display_quota_report(base_olx_dir)
        return

    item_arg = args.item_opt or args.item
    selected_item = choose_item(item_arg)

    # Se a opção escolhida foi verificar cotas
    if selected_item == "cotas":
        display_quota_report(base_olx_dir)
        return

    item_cfg = ITENS_CONFIG[selected_item]
    item_dir = os.path.join(base_olx_dir, item_cfg["pasta"])

    if not os.path.isdir(item_dir):
        raise RuntimeError(f"Pasta do item não encontrada em: {item_dir}")

    print("=" * 68)
    print(f"      REPUBLICADOR AUTOMÁTICO DE ANÚNCIO OLX: {selected_item.upper()}")
    print("=" * 68)

    # 1. Localizar sessão do Firefox e cookies
    print("\n[1/5] Localizando sessão ativa do Firefox Nightly...")
    profile = find_firefox_profile()
    print(f"  Perfil encontrado: {os.path.basename(profile)}")

    cookies = extract_olx_cookies(profile)
    print(f"  Cookies OLX carregados: {len(cookies)} cookies")

    # 2. Consultar anúncios publicados
    scraper = get_scraper()
    print("\n[2/5] Buscando anúncios publicados na conta...")
    ads = fetch_published_ads(scraper, cookies)
    print(f"  Total de anúncios encontrados: {len(ads)}")

    target_ad = match_ad(ads, selected_item)
    is_already_deleted = False

    if not target_ad:
        backup_file = os.path.join(item_dir, "backup_anuncio_antigo.json")
        if os.path.exists(backup_file):
            print("  [i] Anúncio ativo não encontrado na conta, usando backup salvo.")
            with open(backup_file, "r", encoding="utf-8") as f:
                target_ad = json.load(f)
            is_already_deleted = True
        else:
            raise RuntimeError(f"Não foi possível encontrar o anúncio de {selected_item} na conta nem arquivo de backup.")

    ad_id = target_ad.get("adId") or target_ad.get("ad_id")
    list_id = target_ad.get("listId") or target_ad.get("list_id")
    subject = target_ad.get("subject", "") or target_ad.get("title", "")
    price = target_ad.get("price", "")

    print(f"\n  >> ANÚNCIO IDENTIFICADO ({selected_item.upper()}):")
    print(f"     Título:  {subject}")
    print(f"     Preço:   R$ {price}")
    print(f"     List ID: {list_id}")
    print(f"     Ad ID:   {ad_id}")

    # Salva backup dos dados atuais
    backup_path = os.path.join(item_dir, "backup_anuncio_antigo.json")
    if not is_already_deleted:
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(target_ad, f, indent=2, ensure_ascii=False)
        print(f"  Backup salvo em: {os.path.basename(backup_path)}")

    # Informações da Cota Mensal antes da publicação
    quota = get_item_quota_status(base_olx_dir, selected_item)
    print(f"\n  📊 STATUS DA COTA ({quota['mes_nome']}):")
    print(f"     • Categoria: {quota['categoria_nome']} (Limite gratuito: {quota['limite']}/mês)")
    print(f"     • Anúncios já publicados este mês: {quota['usados']}")
    if quota["restantes"] > 0:
        print(f"     • Saldo disponível: Você tem direito a publicar mais {quota['restantes']} anúncio(s) gratuito(s)!")
    else:
        print(f"     • Saldo disponível: ⚠️ Limite gratuito mensal esgotado (0 restantes)!")

    if args.dry_run:
        print("\n[!] Modo DRY-RUN ativado. Nenhuma alteração foi realizada.")
        return

    # Confirmação
    if not args.yes:
        action_msg = "PUBLICAR o anúncio agora" if is_already_deleted else "EXCLUIR este anúncio e PUBLICAR um novo idêntico agora"
        confirm = input(f"\n[?] Deseja {action_msg}? (s/N): ").strip().lower()
        if confirm != "s":
            print("Operação cancelada pelo usuário.")
            return

    # 3. Excluir anúncio antigo (se ainda estiver ativo)
    if not is_already_deleted:
        print(f"\n[3/5] Excluindo anúncio antigo (List ID: {list_id})...")
        delete_ad(scraper, cookies, ad_id, list_id)
        print("  ✓ Anúncio excluído com sucesso!")
        human_delay(3.0, 5.5, "Simulando navegação até a tela de criação", fast=args.fast)
    else:
        print("\n[3/5] Anúncio antigo já estava excluído. Pulando etapa de exclusão.")

    # 4. Upload das novas imagens
    print(f"\n[4/5] Realizando upload das imagens ({selected_item})...")
    uploaded_images = upload_images(scraper, cookies, item_dir, fast=args.fast)

    # 5. Publicar novo anúncio
    print(f"\n[5/5] Publicando novo anúncio de {selected_item} exatamente igual...")
    new_ad_id, res_data = create_ad(scraper, cookies, target_ad, item_dir, uploaded_images, fast=args.fast)
    print(f"  ✓ Anúncio criado com sucesso!")
    print(f"  Novo Ad ID: {new_ad_id}")

    # Registra a publicação no histórico e exibe o saldo de cotas atualizado
    record_quota_publication(base_olx_dir, selected_item, new_ad_id, target_ad.get("listId") or target_ad.get("list_id"), subject)
    quota_pos = get_item_quota_status(base_olx_dir, selected_item)

    print(f"\n  📊 COTA ATUALIZADA ({quota_pos['mes_nome']}):")
    print(f"     • Total utilizado este mês: {quota_pos['usados']} de {quota_pos['limite']}")
    print(f"     • Saldo restante: Você tem direito a mais {quota_pos['restantes']} anúncio(s) gratuito(s) nesta categoria!")

    print("\n" + "=" * 68)
    print("               PROCESSO CONCLUÍDO COM SUCESSO!")
    print("=" * 68)
    print("Você pode verificar seu anúncio atualizado em:")
    print("https://conta.olx.com.br/anuncios/publicados\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERRO]: {e}", file=sys.stderr)
        sys.exit(1)
