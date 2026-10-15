#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de republicação em lote para a OLX.
Executa sequencialmente a exclusão e nova publicação de todos os itens com cota abundante:
  1) Ventilador (Mondial Torre Semi Novo)
  2) Fone (Headset JBL Quantum 400)
  3) Memória RAM (Kingston 8GB DDR4)

Por padrão, NÃO inclui o celular para preservar a cota limitada da categoria (5/mês).
Totalmente autônomo (não solicita confirmações interativas s/N).
Gerencia cotas gratuitas e mantém intervalo de segurança anti-spam entre os anúncios.
"""

import os
import sys
import time
import json
import argparse
import warnings

# Garante que sys.path inclua o diretório atual
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

from republicar_anuncio import (
    ITENS_CONFIG,
    find_olx_base_dir,
    find_firefox_profile,
    extract_olx_cookies,
    get_scraper,
    fetch_published_ads,
    match_ad,
    delete_ad,
    upload_images,
    create_ad,
    record_quota_publication,
    get_item_quota_status,
    display_quota_report,
    human_delay,
)

# Ordem padrão de execução em lote na OLX (exclui celular para proteger cota limitada)
ITENS_PADRAO = ["ventilador", "fone", "memoria"]


def processar_item_olx(scraper, cookies, base_dir, item_key, dry_run=False, fast=False):
    """Executa a rotina de exclusão e republicação para um item individual na OLX."""
    t_start = time.time()
    cfg = ITENS_CONFIG[item_key]
    item_dir = os.path.join(base_dir, cfg["pasta"])

    if not os.path.isdir(item_dir):
        raise RuntimeError(f"Pasta do item não encontrada: {item_dir}")

    # 1. Checagem prévia da cota mensal
    quota = get_item_quota_status(base_dir, item_key)
    print(f"  📊 Cota mensal ({quota['mes_nome']}): {quota['usados']}/{quota['limite']} usados ({quota['restantes']} restantes)")

    if quota["restantes"] <= 0:
        print(f"  ⚠️ Limite gratuito mensal esgotado para '{item_key}'. Pulando este item para evitar cobrança.")
        return {
            "item": item_key,
            "nome": cfg["nome"],
            "status": "COTA ESGOTADA",
            "detalhes": f"0/{quota['limite']} restantes este mês",
            "ad_id": None,
            "elapsed": round(time.time() - t_start, 1),
        }

    # 2. Localizar anúncio antigo na conta
    print("  [1/4] Buscando anúncio atual na conta da OLX...")
    ads = fetch_published_ads(scraper, cookies)
    target_ad = match_ad(ads, item_key)
    is_already_deleted = False

    if not target_ad:
        backup_file = os.path.join(item_dir, "backup_anuncio_antigo.json")
        if os.path.exists(backup_file):
            print("  [i] Anúncio ativo não encontrado na conta, usando backup salvo.")
            with open(backup_file, "r", encoding="utf-8") as f:
                target_ad = json.load(f)
            is_already_deleted = True
        else:
            raise RuntimeError(f"Não foi possível encontrar o anúncio de '{item_key}' na conta nem arquivo de backup.")

    ad_id = target_ad.get("adId") or target_ad.get("ad_id")
    list_id = target_ad.get("listId") or target_ad.get("list_id")
    subject = target_ad.get("subject", "") or target_ad.get("title", "")
    price = target_ad.get("price", "")

    print(f"  >> ANÚNCIO IDENTIFICADO: '{subject}'")
    print(f"     Preço: R$ {price} | List ID: {list_id} | Ad ID: {ad_id}")

    # Salva backup
    backup_path = os.path.join(item_dir, "backup_anuncio_antigo.json")
    if not is_already_deleted:
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(target_ad, f, indent=2, ensure_ascii=False)
            print(f"  Backup salvo em: {os.path.basename(backup_path)}")
        except Exception:
            pass

    if dry_run:
        print(f"  [DRY-RUN] Verificação concluída para '{item_key}'. Nenhuma alteração feita.")
        return {
            "item": item_key,
            "nome": subject or cfg["nome"],
            "status": "DRY-RUN",
            "detalhes": f"List ID: {list_id} | Cota rest.: {quota['restantes']}",
            "ad_id": ad_id,
            "elapsed": round(time.time() - t_start, 1),
        }

    # 3. Excluir anúncio antigo se ativo
    if not is_already_deleted:
        print(f"  [2/4] Excluindo anúncio antigo (List ID: {list_id})...")
        delete_ad(scraper, cookies, ad_id, list_id)
        print("  ✓ Anúncio excluído com sucesso!")
        human_delay(3.0, 5.0, "Aguardando sincronização da exclusão na OLX", fast=fast)
    else:
        print("  [2/4] Anúncio antigo já estava excluído. Pulando etapa de exclusão.")

    # 4. Upload das imagens
    print(f"  [3/4] Fazendo upload das fotos locais ({item_key})...")
    uploaded_images = upload_images(scraper, cookies, item_dir, fast=fast)

    # 5. Publicar novo anúncio
    print(f"  [4/4] Publicando novo anúncio na OLX...")
    new_ad_id, res_data = create_ad(scraper, cookies, target_ad, item_dir, uploaded_images, fast=fast)
    print(f"  ✓ Anúncio criado com sucesso! Novo Ad ID: {new_ad_id}")

    # Registra no histórico de cotas
    record_quota_publication(base_dir, item_key, new_ad_id, target_ad.get("listId") or target_ad.get("list_id"), subject)
    quota_pos = get_item_quota_status(base_dir, item_key)
    print(f"  📊 Cota atualizada: {quota_pos['usados']}/{quota_pos['limite']} usados ({quota_pos['restantes']} restantes)")

    elapsed = round(time.time() - t_start, 1)
    return {
        "item": item_key,
        "nome": subject or cfg["nome"],
        "status": "SUCESSO",
        "detalhes": f"Novo Ad ID: {new_ad_id} | Cota rest.: {quota_pos['restantes']}",
        "ad_id": new_ad_id,
        "elapsed": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Republicar automaticamente os anúncios na OLX em sequência sem o celular e sem confirmação s/N."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas verifica a identificação dos anúncios e cotas sem excluir ou publicar nada.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Desativar pausas humanizadas (modo rápido).",
    )
    parser.add_argument(
        "--delay-min",
        type=float,
        default=6.0,
        help="Tempo mínimo de espera (segundos) entre anúncios (padrão: 6.0s).",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=12.0,
        help="Tempo máximo de espera (segundos) entre anúncios (padrão: 12.0s).",
    )
    parser.add_argument(
        "--incluir-celular",
        action="store_true",
        help="Forçar inclusão do Celular na execução em lote (consome 1 cota de telefonia).",
    )
    parser.add_argument(
        "--itens",
        nargs="+",
        default=None,
        help="Especificar lista customizada de itens (ex: --itens ventilador fone).",
    )
    parser.add_argument(
        "--cotas",
        action="store_true",
        help="Exibir apenas o relatório de cotas mensais e sair.",
    )
    args = parser.parse_args()

    base_dir = find_olx_base_dir()

    if args.cotas:
        display_quota_report(base_dir)
        return

    # Define itens a processar
    if args.itens:
        itens_selecionados = [i.strip().lower() for i in args.itens if i.strip().lower() in ITENS_CONFIG]
    else:
        itens_selecionados = list(ITENS_PADRAO)
        if args.incluir_celular:
            itens_selecionados.append("celular")

    if not itens_selecionados:
        print("[ERRO]: Nenhum item válido selecionado para republicação.", file=sys.stderr)
        sys.exit(1)

    print("=" * 72)
    print("         REPUBLICADOR EM LOTE - OLX (SEM CELULAR)")
    print("=" * 72)
    print(f"Modo: {'DRY-RUN (Simulação)' if args.dry_run else 'EXECUÇÃO REAL (Sem confirmações)'}")
    print(f"Itens na fila ({len(itens_selecionados)}): {', '.join([i.upper() for i in itens_selecionados])}")
    print(f"Intervalo de segurança entre anúncios: {args.delay_min}s a {args.delay_max}s")
    print("Nota: O Celular está excluído deste lote para proteger a cota mensal.")
    print("=" * 72)

    # 1. Carregar sessão e cookies do Firefox Nightly
    print("\n[Início] Localizando sessão ativa do Firefox Nightly...")
    profile = find_firefox_profile()
    print(f"  Perfil: {os.path.basename(profile)}")

    cookies = extract_olx_cookies(profile)
    print(f"  Cookies OLX carregados: {len(cookies)} cookies")

    scraper = get_scraper()
    resultados = []
    t_global_start = time.time()
    total = len(itens_selecionados)

    for idx, item_key in enumerate(itens_selecionados, start=1):
        cfg = ITENS_CONFIG[item_key]
        print("\n" + "#" * 72)
        print(f"  [{idx}/{total}] PROCESSANDO: {cfg['nome'].upper()}")
        print("#" * 72)

        try:
            res = processar_item_olx(scraper, cookies, base_dir, item_key, dry_run=args.dry_run, fast=args.fast)
            resultados.append(res)
        except Exception as e:
            print(f"\n  [!] ERRO ao processar '{item_key}': {e}")
            resultados.append({
                "item": item_key,
                "nome": cfg["nome"],
                "status": "FALHA",
                "detalhes": str(e),
                "ad_id": None,
                "elapsed": 0.0,
            })

        # Intervalo anti-spam entre anúncios (exceto após o último item)
        if idx < total and not args.dry_run:
            human_delay(
                args.delay_min,
                args.delay_max,
                f"Aguardando intervalo de segurança antes do item {idx + 1}/{total}",
                fast=args.fast,
            )

    total_elapsed = round(time.time() - t_global_start, 1)

    # Relatório Final
    print("\n" + "=" * 72)
    print("                    RELATÓRIO FINAL DA REPUBLICAÇÃO (OLX)")
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
    print(f"Tempo total decorrido: {total_elapsed}s | Sucessos: {sucessos}/{total}")
    print("Verifique seus anúncios atualizados em:")
    print("https://conta.olx.com.br/anuncios/publicados\n")
    print("=" * 72)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERRO FATAL]: {e}", file=sys.stderr)
        sys.exit(1)
