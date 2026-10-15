#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de republicação em lote para o Facebook Marketplace.
Executa sequencialmente a exclusão e nova publicação de todos os itens cadastrados:
  1) Celular (Samsung Galaxy S23)
  2) Ventilador (Mondial Torre Semi Novo)
  3) Fone (Headset JBL Quantum 400)
  4) Memória RAM (Kingston 8GB DDR4)

Totalmente autônomo (não solicita confirmações interativas s/N).
Mantém intervalo de segurança (cooldown anti-spam) entre os anúncios.
"""

import os
import sys
import time
import argparse
import warnings

# Garante que sys.path inclua o diretório atual e o diretório base
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Configura codificação do console para UTF-8 no Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

warnings.filterwarnings("ignore")

from playwright.sync_api import sync_playwright

from republicar_marketplace import (
    ITENS_CONFIG,
    find_marketplace_base_dir,
    find_firefox_profile,
    extract_facebook_cookies,
    load_item_data,
    find_old_ad,
    delete_old_ad,
    publish_new_ad,
    human_delay,
)

# Ordem padrão de execução em lote
ITENS_PADRAO = ["celular", "ventilador", "fone", "memoria"]


def processar_item(page, base_dir, item_key, dry_run=False, fast=False):
    """Executa a rotina de exclusão e republicação para um item individual."""
    t_start = time.time()
    cfg = ITENS_CONFIG[item_key]
    item_data = load_item_data(base_dir, item_key)

    # 1. Localizar anúncio antigo em 'Seus classificados'
    found, more_btn, target_title = find_old_ad(page, item_key, item_data)

    if dry_run:
        print(f"\n  [DRY-RUN] Verificação concluída para '{item_key}'. Nenhuma alteração feita.")
        elapsed = round(time.time() - t_start, 1)
        return {
            "item": item_key,
            "nome": item_data["title"],
            "status": "DRY-RUN",
            "detalhes": f"Anúncio anterior: {target_title or 'Nenhum ativo'}",
            "elapsed": elapsed,
        }

    # 2. Excluir anúncio antigo (se existir)
    if found and more_btn:
        delete_old_ad(page, more_btn, target_title, item_data, fast=fast)
    else:
        print("\n[3/5] Anúncio antigo não encontrado ou já excluído. Pulando exclusão.")

    # 3. Publicar novo anúncio
    publish_new_ad(page, item_data, fast=fast)

    elapsed = round(time.time() - t_start, 1)
    return {
        "item": item_key,
        "nome": item_data["title"],
        "status": "SUCESSO",
        "detalhes": "Excluído e republicado com sucesso",
        "elapsed": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Republicar automaticamente TODOS os itens no Facebook Marketplace em sequência (sem confirmação s/N)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas verifica a identificação dos anúncios sem excluir ou publicar nada.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Executar com a janela do navegador visível.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Desativar pausas humanizadas (modo rápido).",
    )
    parser.add_argument(
        "--delay-min",
        type=float,
        default=8.0,
        help="Tempo mínimo de espera (segundos) entre anúncios (padrão: 8.0s).",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=15.0,
        help="Tempo máximo de espera (segundos) entre anúncios (padrão: 15.0s).",
    )
    parser.add_argument(
        "--itens",
        nargs="+",
        default=ITENS_PADRAO,
        help=f"Lista de itens a processar (padrão: {' '.join(ITENS_PADRAO)}).",
    )
    args = parser.parse_args()

    # Validação dos itens informados
    itens_validos = []
    for it in args.itens:
        it_clean = it.strip().lower()
        if it_clean in ITENS_CONFIG:
            itens_validos.append(it_clean)
        else:
            print(f"[!] Aviso: Item '{it}' não reconhecido. Opções válidas: {list(ITENS_CONFIG.keys())}")

    if not itens_validos:
        print("[ERRO]: Nenhum item válido selecionado para republicação.", file=sys.stderr)
        sys.exit(1)

    base_dir = find_marketplace_base_dir()

    print("=" * 72)
    print("      REPUBLICADOR TOTAL AUTOMÁTICO - FACEBOOK MARKETPLACE")
    print("=" * 72)
    print(f"Modo: {'DRY-RUN (Simulação)' if args.dry_run else 'EXECUÇÃO REAL (Sem confirmações)'}")
    print(f"Itens na fila ({len(itens_validos)}): {', '.join([i.upper() for i in itens_validos])}")
    print(f"Cooldown entre itens: {args.delay_min}s a {args.delay_max}s")
    print(f"Navegador: {'Visível (Headed)' if args.headed else 'Segundo plano (Headless)'}")
    print("=" * 72)

    # 1. Carregar perfil e cookies do Firefox Nightly
    print("\n[Início] Localizando sessão ativa do Firefox Nightly...")
    profile = find_firefox_profile()
    print(f"  Perfil: {os.path.basename(profile)}")

    cookies = extract_facebook_cookies(profile)
    print(f"  Cookies do Facebook carregados: {len(cookies)} cookies")

    headless_mode = not args.headed
    resultados = []
    t_global_start = time.time()

    with sync_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
        ]
        browser = p.chromium.launch(headless=headless_mode, args=launch_args)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={"width": 1280, "height": 800},
        )
        context.add_cookies(cookies)

        # Injeta evasões anti-detecção
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

        # Aceita eventuais caixas de diálogo inesperadas para não travar o fluxo
        page.on("dialog", lambda dialog: dialog.accept())

        total = len(itens_validos)
        for idx, item_key in enumerate(itens_validos, start=1):
            cfg = ITENS_CONFIG[item_key]
            print("\n" + "#" * 72)
            print(f"  [{idx}/{total}] PROCESSANDO: {cfg['nome'].upper()}")
            print("#" * 72)

            try:
                res = processar_item(page, base_dir, item_key, dry_run=args.dry_run, fast=args.fast)
                resultados.append(res)
            except Exception as e:
                print(f"\n  [!] ERRO ao processar '{item_key}': {e}")
                resultados.append({
                    "item": item_key,
                    "nome": cfg["nome"],
                    "status": "FALHA",
                    "detalhes": str(e),
                    "elapsed": 0.0,
                })

            # Intervalo de segurança anti-spam entre anúncios (exceto após o último item)
            if idx < total and not args.dry_run:
                human_delay(
                    args.delay_min,
                    args.delay_max,
                    f"Aguardando intervalo anti-spam antes do item {idx + 1}/{total}",
                    fast=args.fast,
                )

        browser.close()

    total_elapsed = round(time.time() - t_global_start, 1)

    # Relatório Final
    print("\n" + "=" * 72)
    print("                    RELATÓRIO FINAL DA REPUBLICAÇÃO")
    print("=" * 72)
    print(f"{'Item':<12} | {'Status':<10} | {'Tempo':<7} | {'Detalhes'}")
    print("-" * 72)

    sucessos = 0
    for r in resultados:
        status_ico = "✓ " if r["status"] in ("SUCESSO", "DRY-RUN") else "✗ "
        status_text = status_ico + r["status"]
        if r["status"] == "SUCESSO":
            sucessos += 1
        print(f"{r['item'].capitalize():<12} | {status_text:<10} | {str(r['elapsed']) + 's':<7} | {r['detalhes']}")

    print("-" * 72)
    print(f"Tempo total decorrido: {total_elapsed}s | Sucessos: {sucessos}/{len(itens_validos)}")
    print("Verifique seus classificados atualizados em:")
    print("https://www.facebook.com/marketplace/you/selling\n")
    print("=" * 72)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERRO FATAL]: {e}", file=sys.stderr)
        sys.exit(1)
