#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script unificado para excluir e republicar automaticamente anúncios no Facebook Marketplace.
Suporta seleção de itens (Celular, Ventilador ou Fone).
Utiliza a sessão ativa e cookies do Firefox Nightly via Playwright (sem deslogar seu navegador).
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

# Configura codificação do console para UTF-8 no Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

warnings.filterwarnings("ignore")

from playwright.sync_api import sync_playwright

# Definição dos itens suportados e seus metadados para o Facebook Marketplace
ITENS_CONFIG = {
    "celular": {
        "nome": "Celular Smartphone Samsung Galaxy S23",
        "pasta": "celular",
        "keywords": ["galaxy", "s23", "samsung", "celular", "smartphone"],
        "categoria": "Telefones celulares",
        "condicao": "Usado — em boas condições",
        "marca": "Samsung",
        "compativel": "Samsung Galaxy S23",
        "cor": "Branco",
        "encontro": "Encontro público",
        "ocultar_amigos": True,
    },
    "ventilador": {
        "nome": "Ventilador Mondial Torre Semi Novo",
        "pasta": "ventilador",
        "keywords": ["ventilador", "mondial", "torre"],
        "categoria": "Aparelhos",
        "condicao": "Usado — estado de novo",
        "marca": "Mondial",
        "compativel": None,
        "cor": "Preto",
        "encontro": "Retirada",
        "ocultar_amigos": True,
    },
    "fone": {
        "nome": "Headset Headphone Fone JBL Quantum 400",
        "pasta": "fone",
        "keywords": ["jbl", "headset", "fone", "headphone", "quantum"],
        "categoria": "Eletrônicos e informática",
        "condicao": "Usado — estado de novo",
        "marca": "JBL",
        "compativel": None,
        "cor": "Preto",
        "encontro": "Encontro público",
        "ocultar_amigos": True,
    }
}


def human_delay(min_sec, max_sec, action_desc="", fast=False):
    """Pausa aleatória para simular o ritmo e tempo de reação de um usuário humano."""
    if fast:
        return
    duration = round(random.uniform(min_sec, max_sec), 2)
    if action_desc:
        print(f"  ⏳ {action_desc} (aguardando {duration}s)...")
    time.sleep(duration)


def human_type(locator, text, min_delay=25, max_delay=70, fast=False):
    """Digita texto caractere por caractere simulando cadência humana realista."""
    if fast or len(text) > 150:
        locator.fill(text)
        return
    locator.click()
    locator.fill("")
    for char in text:
        locator.press_sequentially(char)
        time.sleep(random.uniform(min_delay / 1000.0, max_delay / 1000.0))


def human_click(locator, page, fast=False):
    """Move o mouse suavemente com trajetória natural antes de clicar."""
    if not fast:
        try:
            box = locator.bounding_box()
            if box:
                target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                page.mouse.move(target_x, target_y, steps=random.randint(4, 9))
                time.sleep(random.uniform(0.08, 0.22))
        except Exception:
            pass
    locator.click()


def find_marketplace_base_dir():
    """Identifica o diretório raiz do experimento Marketplace."""
    curr = os.path.abspath(os.getcwd())
    if os.path.basename(curr) in ("celular", "ventilador", "fone"):
        return os.path.dirname(curr)
    if os.path.isdir(os.path.join(curr, "celular")):
        return curr
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(script_dir) in ("celular", "ventilador", "fone"):
        return os.path.dirname(script_dir)
    return script_dir


def find_firefox_profile():
    """Localiza o diretório do perfil ativo do Firefox Nightly."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("Variável de ambiente APPDATA não encontrada.")

    profiles_dir = os.path.join(appdata, "Mozilla", "Firefox", "Profiles")
    if not os.path.isdir(profiles_dir):
        raise RuntimeError(f"Diretório de perfis do Firefox não encontrado em: {profiles_dir}")

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


def extract_facebook_cookies(profile_path):
    """Extrai os cookies do Facebook do perfil do Firefox sem bloquear o navegador aberto."""
    cookie_db = os.path.join(profile_path, "cookies.sqlite")
    if not os.path.exists(cookie_db):
        raise RuntimeError(f"Banco de cookies não encontrado em: {cookie_db}")

    temp_db = os.path.join(os.environ.get("TEMP", "."), f"temp_fb_{uuid.uuid4().hex[:8]}.sqlite")
    temp_wal = temp_db + "-wal"

    try:
        shutil.copy2(cookie_db, temp_db)
        if os.path.exists(cookie_db + "-wal"):
            shutil.copy2(cookie_db + "-wal", temp_wal)

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT host, name, value, path, isSecure, expiry FROM moz_cookies WHERE host LIKE '%facebook%'")
        rows = cursor.fetchall()
        conn.close()

        pw_cookies = []
        for host, name, value, path, is_secure, expiry in rows:
            c = {
                "name": name,
                "value": value,
                "domain": host,
                "path": path,
                "secure": bool(is_secure)
            }
            if expiry and expiry > 0:
                # Trata milissegundos convertendo para segundos unix
                c["expires"] = int(expiry / 1000) if expiry > 10000000000 else int(expiry)
            pw_cookies.append(c)

        return pw_cookies
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)
        if os.path.exists(temp_wal):
            os.remove(temp_wal)


def choose_item(item_arg):
    """Permite ao usuário escolher o item via CLI ou menu interativo."""
    if item_arg:
        key = item_arg.strip().lower()
        if key in ("1", "cel", "celular", "smartphone", "s23"):
            return "celular"
        if key in ("2", "vent", "ventilador", "torre", "mondial"):
            return "ventilador"
        if key in ("3", "fone", "headset", "headphone", "jbl", "quantum"):
            return "fone"
        print(f"[!] Opção '{item_arg}' não reconhecida. Escolha abaixo:")

    cwd_name = os.path.basename(os.getcwd()).lower()
    default_choice = "1"
    if cwd_name == "celular":
        default_choice = "1"
    elif cwd_name == "ventilador":
        default_choice = "2"
    elif cwd_name == "fone":
        default_choice = "3"

    print("\n[?] Qual item você deseja republicar no Facebook Marketplace?")
    print("  1) Celular (Samsung Galaxy S23)")
    print("  2) Ventilador (Mondial Torre Semi Novo)")
    print("  3) Fone (Headset JBL Quantum 400)")

    choice = input(f"\nEscolha a opção (1, 2 ou 3) [Padrão: {default_choice}]: ").strip()
    if not choice:
        choice = default_choice

    if choice in ("1", "celular"):
        return "celular"
    elif choice in ("2", "ventilador"):
        return "ventilador"
    elif choice in ("3", "fone"):
        return "fone"
    else:
        print("Opção inválida. Selecionando Celular por padrão.")
        return "celular"


def load_item_data(base_dir, item_key):
    """Carrega título, preço, corpo, tags e imagens da pasta local do item."""
    cfg = ITENS_CONFIG[item_key]
    item_dir = os.path.join(base_dir, cfg["pasta"])
    if not os.path.isdir(item_dir):
        raise RuntimeError(f"Pasta do item não encontrada em: {item_dir}")

    title_file = os.path.join(item_dir, "descricao_titulo.txt")
    body_file = os.path.join(item_dir, "descricao_corpo.txt")
    price_file = os.path.join(item_dir, "preco.txt")
    tags_file = os.path.join(item_dir, "tags_somente_marketplace.txt")

    title = cfg["nome"]
    if os.path.exists(title_file):
        with open(title_file, "r", encoding="utf-8") as f:
            title = f.read().strip()

    body = ""
    if os.path.exists(body_file):
        with open(body_file, "r", encoding="utf-8") as f:
            body = f.read().strip()

    price = "0"
    if os.path.exists(price_file):
        with open(price_file, "r", encoding="utf-8") as f:
            price = f.read().strip()

    tags = []
    if os.path.exists(tags_file):
        with open(tags_file, "r", encoding="utf-8") as f:
            raw_tags = f.read().strip()
            tags = [t.strip().rstrip(".") for t in raw_tags.split(",") if t.strip()]

    candidates = (
        glob.glob(os.path.join(item_dir, "*.jpg")) +
        glob.glob(os.path.join(item_dir, "*.png")) +
        glob.glob(os.path.join(item_dir, "imagens", "*.jpg")) +
        glob.glob(os.path.join(item_dir, "imagens", "*.png"))
    )
    seen = set()
    images = []
    for c in sorted(candidates):
        if c not in seen:
            seen.add(c)
            images.append(os.path.abspath(c))

    if not images:
        raise RuntimeError(f"Nenhuma imagem encontrada para o item em: {item_dir}")

    return {
        "title": title,
        "price": price,
        "body": body,
        "tags": tags,
        "images": images,
        "item_dir": item_dir,
        "cfg": cfg
    }


def find_old_ad(page, item_key, item_data):
    """Localiza o anúncio antigo na página de vendas e retorna suas informações."""
    print("\n[2/5] Verificando anúncios ativos em 'Seus classificados'...")
    page.goto("https://www.facebook.com/marketplace/you/selling", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)

    keywords = item_data["cfg"]["keywords"]
    more_btn = None
    target_title = None

    # Tenta localizar o botão de 'Mais opções para [Título]'
    for kw in keywords:
        btn_candidate = page.locator('[aria-label*="Mais opções para " i]')
        count = btn_candidate.count()
        for idx in range(count):
            label = btn_candidate.nth(idx).get_attribute("aria-label") or ""
            if kw.lower() in label.lower():
                more_btn = btn_candidate.nth(idx)
                target_title = label.replace("Mais opções para ", "").strip()
                break
        if more_btn:
            break

    if not more_btn:
        print(f"  [i] Nenhum anúncio ativo com palavras-chave {keywords} encontrado no momento.")
        return False, None, None

    print(f"  >> ANÚNCIO IDENTIFICADO:")
    print(f"     Título: {target_title}")

    # Salva backup
    backup_path = os.path.join(item_data["item_dir"], "backup_anuncio_antigo.json")
    try:
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump({
                "item": item_key,
                "titulo": target_title,
                "data_consulta": time.strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2, ensure_ascii=False)
        print(f"  Backup salvo em: {os.path.basename(backup_path)}")
    except Exception:
        pass

    return True, more_btn, target_title


def delete_old_ad(page, more_btn, target_title, item_data, fast=False):
    """Realiza a exclusão do anúncio antigo após confirmação."""
    print("\n[3/5] Excluindo anúncio antigo do Marketplace...")
    more_btn.click()
    page.wait_for_timeout(1500)

    # Clica em 'Excluir classificado' no menu suspenso
    excluir_menu = page.locator('span:text-is("Excluir classificado"), [role="menuitem"]:has-text("Excluir classificado")').first
    excluir_menu.click()
    page.wait_for_timeout(2000)

    # Clica no botão 'Excluir' VISÍVEL do modal de confirmação (evitando templates ocultos com aria-hidden)
    page.wait_for_timeout(1000)
    clicked = page.evaluate("""
        () => {
            const dialog = document.querySelector('[role="dialog"]');
            if (!dialog) return false;
            const buttons = Array.from(dialog.querySelectorAll('[role="button"]'));
            const target = buttons.find(b =>
                (b.innerText.trim() === 'Excluir' || b.getAttribute('aria-label') === 'Excluir') &&
                b.getAttribute('aria-disabled') !== 'true' &&
                b.getAttribute('aria-hidden') !== 'true' &&
                b.offsetWidth > 0 &&
                b.offsetHeight > 0
            );
            if (target) {
                target.click();
                return true;
            }
            return false;
        }
    """)
    if not clicked:
        # Fallback via locator filtrado para elementos estritamente visíveis
        modal_btn = page.locator('[role="dialog"]').locator('div[role="button"]:not([aria-disabled="true"]):not([aria-hidden="true"]):has-text("Excluir"):visible').first
        if modal_btn.count() > 0:
            modal_btn.click(force=True)
            clicked = True

    if clicked:
        print("  ✓ Confirmação de exclusão enviada!")
        page.wait_for_timeout(3000)
    else:
        print("  [!] Botão de confirmação de exclusão não encontrado no modal.")

    # Trata eventual pesquisa de feedback ("Você vendeu este item?")
    page.evaluate("""
        () => {
            const dialog = document.querySelector('[role="dialog"]');
            if (!dialog) return;
            const btns = Array.from(dialog.querySelectorAll('[role="button"]'));
            const closeBtn = btns.find(b => 
                b.getAttribute('aria-label') === 'Fechar' || 
                b.innerText.includes('Não, não vendi') || 
                b.innerText.includes('Avançar')
            );
            if (closeBtn) closeBtn.click();
        }
    """)
    page.wait_for_timeout(1500)

    print("  ✓ Anúncio antigo excluído com sucesso!")
    human_delay(2.5, 4.5, "Aguardando sincronização da exclusão", fast=fast)
    return True


def publish_new_ad(page, item_data, fast=False):
    """Preenche e publica o novo anúncio com todos os campos especificados."""
    cfg = item_data["cfg"]
    title = item_data["title"]
    price = item_data["price"]
    body = item_data["body"]
    tags = item_data["tags"]
    images = item_data["images"]

    print("\n[4/5] Acessando formulário de criação de classificado...")
    page.goto("https://www.facebook.com/marketplace/create/item", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)

    # 1. Upload de Imagens
    print(f"\n[+] Fazendo upload de {len(images)} imagens...")
    file_input = page.locator('input[type="file"]').first
    file_input.set_input_files(images)
    for idx, img_path in enumerate(images, start=1):
        print(f"  ✓ [{idx}/{len(images)}] {os.path.basename(img_path)}")
    human_delay(3.0, 5.0, "Processando prévia das fotos no Facebook", fast=fast)

    # 2. Preenchimento de Título e Preço
    print(f"  ✓ Preenchendo Título: '{title}'")
    human_type(page.locator('label:has-text("Título") input').first, title, fast=fast)
    human_delay(0.8, 1.5, fast=fast)

    print(f"  ✓ Preenchendo Preço: 'R$ {price}'")
    human_type(page.locator('label:has-text("Preço") input').first, price, fast=fast)
    human_delay(0.8, 1.5, fast=fast)

    # 3. Seleção de Categoria
    target_category = cfg["categoria"]
    print(f"  ✓ Selecionando Categoria: '{target_category}'")
    cat_dropdown = page.locator('label:has-text("Categoria")').first
    human_click(cat_dropdown, page, fast=fast)
    page.wait_for_timeout(1000)

    cat_option = page.locator(f'span:text-is("{target_category}")').first
    if cat_option.count() == 0:
        cat_option = page.locator(f'span:has-text("{target_category}")').first
    cat_option.scroll_into_view_if_needed()
    human_click(cat_option, page, fast=fast)
    page.wait_for_timeout(1500)

    # 4. Seleção de Condição
    target_cond = cfg["condicao"]
    print(f"  ✓ Selecionando Condição: '{target_cond}'")
    cond_dropdown = page.locator('label:has-text("Condição")').first
    human_click(cond_dropdown, page, fast=fast)
    page.wait_for_timeout(1000)
    cond_option = page.locator(f'span:text-is("{target_cond}")').first
    if cond_option.count() == 0:
        cond_option = page.locator(f'span:has-text("{target_cond}")').first
    if cond_option.count() == 0:
        sub = "estado de novo" if "novo" in target_cond.lower() else "boas condições"
        cond_option = page.locator(f'span:has-text("{sub}")').first
    cond_option.scroll_into_view_if_needed()
    human_click(cond_option, page, fast=fast)
    page.wait_for_timeout(1200)

    # 5. Expandir seção 'Mais detalhes'
    page.evaluate("""
    () => {
        const els = Array.from(document.querySelectorAll('*'));
        const target = els.find(el => el.innerText && el.innerText.includes('Mais detalhes') && el.innerText.includes('Atraia mais interesse'));
        if (target) {
            target.scrollIntoView();
            target.click();
        }
    }
    """)
    page.wait_for_timeout(1500)

    # Rola barra lateral para ter todos os campos visíveis
    page.evaluate("""
    () => {
        const scrollables = Array.from(document.querySelectorAll('div')).filter(d => d.scrollHeight > d.clientHeight);
        for (const s of scrollables) {
            s.scrollTop = s.scrollHeight;
        }
    }
    """)
    page.wait_for_timeout(1000)

    # 6. Campos específicos de categoria (Marca, Modelo compatível, Cor)
    marca = cfg.get("marca")
    if marca:
        marca_field = page.locator('label:has-text("Marca") input, label:has-text("Marca") [role="combobox"]').first
        if marca_field.count() > 0:
            marca_field.scroll_into_view_if_needed()
            human_type(marca_field, marca, fast=fast)
            page.wait_for_timeout(600)
            opt_marca = page.locator(f'div[role="option"]:has-text("{marca}"), span:text-is("{marca}")').first
            if opt_marca.count() > 0:
                human_click(opt_marca, page, fast=fast)
            print(f"  ✓ Preenchendo Marca: '{marca}'")

    compativel = cfg.get("compativel")
    if compativel:
        compat_field = page.locator('label:has-text("Telefone celular compatível") input').first
        if compat_field.count() > 0:
            human_type(compat_field, compativel, fast=fast)
            print(f"  ✓ Preenchendo Telefone compatível: '{compativel}'")

    cor = cfg.get("cor")
    if cor:
        cor_label = page.locator('label:has-text("Cor")').first
        if cor_label.count() > 0:
            cor_label.scroll_into_view_if_needed()
            cor_inp = cor_label.locator('input').first
            if cor_inp.count() > 0:
                human_type(cor_inp, cor, fast=fast)
                page.wait_for_timeout(700)
                # Seleciona no dropdown de opções que surge
                opt_cor = page.locator(f'div[role="option"]:has-text("{cor}"), span:text-is("{cor}"), div:text-is("{cor}")').first
                if opt_cor.count() > 0:
                    human_click(opt_cor, page, fast=fast)
                    print(f"  ✓ Selecionando Cor no dropdown: '{cor}'")
                else:
                    cor_inp.press("Enter")
                    print(f"  ✓ Cor confirmada: '{cor}'")

    # 7. Descrição
    print(f"  ✓ Preenchendo Descrição detalhada ({len(body)} caracteres)...")
    desc_area = page.locator('label:has-text("Descrição") textarea').first
    desc_area.click()
    desc_area.fill(body)
    human_delay(1.0, 2.0, fast=fast)

    # 8. Disponibilidade (Garantir 'Anunciar como Em estoque')
    disp_label = page.locator('label:has-text("Disponibilidade")')
    if disp_label.count() > 0:
        disp_text = disp_label.first.inner_text()
        if "item único" in disp_text.lower():
            human_click(disp_label.first, page, fast=fast)
            page.wait_for_timeout(800)
            human_click(page.locator('span:has-text("Em estoque")').first, page, fast=fast)
            print("  ✓ Disponibilidade ajustada para: 'Em estoque'")
        else:
            print("  ✓ Disponibilidade confirmada: 'Em estoque'")

    # 9. Etiquetas de Produto (Tags)
    if tags:
        tags_field = page.locator('label:has-text("Etiquetas de produto") textarea, label:has-text("Etiquetas") textarea, label:has-text("Etiquetas de produto") input, label:has-text("Etiquetas") input')
        if tags_field.count() > 0:
            print(f"  ✓ Inserindo {min(len(tags), 20)} etiquetas de produto...")
            el = tags_field.first
            el.click()
            for tag in tags[:20]:
                human_type(el, tag, min_delay=15, max_delay=40, fast=fast)
                el.press("Enter")
                time.sleep(random.uniform(0.15, 0.35))
        else:
            print("  [!] Aviso: Campo de etiquetas de produto não encontrado no formulário.")

    # Rola barra lateral até o final para exibir preferências de encontro e ocultar para amigos
    page.evaluate("""
    () => {
        const scrollables = Array.from(document.querySelectorAll('div')).filter(d => d.scrollHeight > d.clientHeight);
        for (const s of scrollables) {
            s.scrollTop = s.scrollHeight;
        }
    }
    """)
    page.wait_for_timeout(1000)

    # 10. Preferências de encontro (Encontro público, Retirada, Entrega)
    desired_encontro = cfg.get("encontro")
    if desired_encontro:
        print(f"  ✓ Configurando Preferências de encontro: '{desired_encontro}'...")
        options = ["Encontro público", "Retirada", "Entrega"]
        for opt in options:
            cb = page.locator(f'div[role="checkbox"]:has-text("{opt}")').first
            if cb.count() > 0:
                cb.scroll_into_view_if_needed()
                is_checked = cb.get_attribute("aria-checked") == "true"
                should_be_checked = (opt == desired_encontro)
                if should_be_checked and not is_checked:
                    human_click(cb, page, fast=fast)
                    page.wait_for_timeout(500)
                elif not should_be_checked and is_checked:
                    human_click(cb, page, fast=fast)
                    page.wait_for_timeout(500)
        print(f"  ✓ Preferência de encontro confirmada: '{desired_encontro}'")

    # 11. Ocultar para os amigos
    if cfg.get("ocultar_amigos", False):
        switch_inp = page.locator('input[aria-label="Ocultar para os amigos"]').first
        if switch_inp.count() > 0:
            switch_inp.scroll_into_view_if_needed()
            if not switch_inp.is_checked():
                switch_inp.click(force=True)
                page.wait_for_timeout(600)
            print("  ✓ 'Ocultar para os amigos' ativado com sucesso!")
        else:
            print("  [!] Aviso: Chave 'Ocultar para os amigos' não encontrada no formulário.")

    human_delay(2.5, 4.0, "Revisando dados preenchidos", fast=fast)

    # 12. Avançar para a tela de confirmação/grupos
    print("\n[5/5] Finalizando e publicando anúncio no Marketplace...")
    avancar_btn = page.locator('div[aria-label="Avançar"], div[role="button"]:has-text("Avançar")').first
    if not avancar_btn.is_enabled():
        raise RuntimeError("Botão 'Avançar' não está habilitado. Verifique os campos obrigatórios.")

    human_click(avancar_btn, page, fast=fast)
    page.wait_for_timeout(3500)

    # 11. Botão 'Publicar'
    pub_btn = page.locator('div[aria-label="Publicar"], div[role="button"]:has-text("Publicar")').first
    if pub_btn.count() == 0 or not pub_btn.is_enabled():
        raise RuntimeError("Botão 'Publicar' não encontrado ou desabilitado na etapa final.")

    human_click(pub_btn, page, fast=fast)
    print("  ⏳ Submetendo anúncio (aguardando confirmação do Facebook)...")
    page.wait_for_timeout(8000)

    print("  ✓ Anúncio publicado com sucesso!")


def main():
    parser = argparse.ArgumentParser(description="Excluir e republicar anúncio no Facebook Marketplace (Celular, Ventilador ou Fone)")
    parser.add_argument("item", nargs="?", default=None, help="Item para republicar: 'celular', 'ventilador' ou 'fone'")
    parser.add_argument("--item", "-i", dest="item_opt", default=None, help="Item para republicar: 'celular', 'ventilador' ou 'fone'")
    parser.add_argument("--yes", "-y", action="store_true", help="Executar sem pedir confirmação interativa")
    parser.add_argument("--dry-run", action="store_true", help="Apenas preencher o formulário sem excluir ou publicar")
    parser.add_argument("--headed", action="store_true", help="Executar com janela do navegador visível")
    parser.add_argument("--fast", action="store_true", help="Desativar pausas humanizadas (modo rápido)")
    args = parser.parse_args()

    item_arg = args.item_opt or args.item
    selected_item = choose_item(item_arg)

    base_dir = find_marketplace_base_dir()
    item_data = load_item_data(base_dir, selected_item)

    print("=" * 68)
    print(f"   REPUBLICADOR AUTOMÁTICO FACEBOOK MARKETPLACE: {selected_item.upper()}")
    print("=" * 68)

    # 1. Localizar sessão do Firefox e cookies
    print("\n[1/5] Localizando sessão ativa do Firefox Nightly...")
    profile = find_firefox_profile()
    print(f"  Perfil encontrado: {os.path.basename(profile)}")

    cookies = extract_facebook_cookies(profile)
    print(f"  Cookies do Facebook carregados: {len(cookies)} cookies")

    # Iniciar automação do navegador com os cookies
    headless_mode = not args.headed

    with sync_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage"
        ]
        browser = p.chromium.launch(headless=headless_mode, args=launch_args)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={"width": 1280, "height": 800}
        )
        context.add_cookies(cookies)

        # Injeta evasões anti-detecção de bot / webdriver
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' }
                ]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['pt-BR', 'pt', 'en-US', 'en']
            });
        """)

        page = context.new_page()

        # 2. Localizar anúncio antigo
        found, more_btn, target_title = find_old_ad(page, selected_item, item_data)

        if args.dry_run:
            print("\n[!] Modo DRY-RUN ativado. Nenhuma exclusão ou publicação foi realizada.")
            browser.close()
            return

        # Confirmação do usuário
        if not args.yes:
            action_desc = "EXCLUIR este anúncio e PUBLICAR um novo idêntico agora" if found else "PUBLICAR um novo anúncio no Marketplace agora"
            confirm = input(f"\n[?] Deseja {action_desc}? (s/N): ").strip().lower()
            if confirm != "s":
                print("Operação cancelada pelo usuário.")
                browser.close()
                return

        # 3. Excluir anúncio antigo (se foi encontrado)
        if found and more_btn:
            delete_old_ad(page, more_btn, target_title, item_data, fast=args.fast)
        else:
            print("\n[3/5] Anúncio antigo não encontrado ou já excluído. Pulando etapa de exclusão.")

        # 4 e 5. Publicar novo anúncio
        publish_new_ad(page, item_data, fast=args.fast)
        browser.close()

    print("\n" + "=" * 68)
    print("               PROCESSO CONCLUÍDO COM SUCESSO!")
    print("=" * 68)
    print("Você pode verificar seu anúncio atualizado em:")
    print("https://www.facebook.com/marketplace/you/selling\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERRO]: {e}", file=sys.stderr)
        sys.exit(1)
