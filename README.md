# 📦 vender_usados

Scripts de automação para exclusão e republicação periódica de anúncios de itens usados na **OLX** e no **Facebook Marketplace**, utilizando as sessões ativas do **Firefox Nightly** (sem deslogar do navegador).

---

## 📂 Estrutura do Repositório

```text
vender_usados/
├── olx/
│   ├── celular/                         # Celular Samsung Galaxy S23 (5 anúncios grátis/mês)
│   ├── ventilador/                      # Ventilador Mondial Torre (20 anúncios grátis/mês)
│   ├── fone/                            # Headset JBL Quantum 400 (20 anúncios grátis/mês)
│   ├── lombar_mckenzie/                 # Suporte Lombar McKenzie SlimLine Roll (20 anúncios grátis/mês)
│   ├── lombar_xt_racer/                 # Suporte Lombar XT Racer Original Cinza (20 anúncios grátis/mês)
│   ├── cercadinho/                      # [VENDIDO] Cercadinho Galzerano (arquivado)
│   ├── republicar_anuncio.py            # Automação individual via API direta da OLX + Gestão de Cotas
│   ├── republicar_tudo.py               # Republicador sequencial em lote (ventilador, fone e suportes - sem celular)
│   ├── republicar_tudo.bat              # Atalho executável para o republicar_tudo.py da OLX
│   ├── historico_cotas.json             # Histórico e saldo de cotas de anúncios gratuitos
│   └── ESTRATEGIA_REPUBLICACAO_OUTUBRO_2026.md # Planejamento estratégico de reupagem
│
├── marketplace/
│   ├── celular/                         # Metadados, fotos e tags do celular
│   ├── ventilador/                      # Metadados, fotos e tags do ventilador
│   ├── fone/                            # Metadados, fotos e tags do fone
│   ├── lombar_mckenzie/                 # Metadados, fotos e tags do suporte McKenzie
│   ├── lombar_xt_racer/                 # Metadados, fotos e tags do suporte XT Racer
│   ├── cercadinho/                      # [VENDIDO] Cercadinho Galzerano (arquivado)
│   ├── republicar_marketplace.py        # Automação individual via Playwright Chromium + Stealth
│   ├── republicar_tudo.py               # Republicador sequencial em lote dos 5 itens ativos (sem confirmações)
│   └── republicar_tudo.bat              # Atalho executável para o republicar_tudo.py
│
├── .gitignore
└── README.md
```

---

## ⚡ 1. OLX (`olx/`)

Automação construída com chamadas diretas às APIs internas da OLX (`cloudscraper`), dispensando navegador em segundo plano e evitando bloqueios de Cloudflare e telas de upsell.

### Recursos:
- **Extração Segura de Cookies:** Lê os tokens e sessão do perfil ativo do Firefox Nightly sem bloquear ou travar o navegador.
- **Gerenciador de Cotas Gratuitas:** Controla o limite mensal oficial da OLX por categoria e alerta antes e depois da publicação sobre quantos anúncios gratuitos ainda restam no mês.
- **Alternância Automática de Categorias:** Para itens com múltiplos públicos (como os suportes lombares), o script reveza automaticamente a cada ciclo entre categorias complementares (ex: *Saúde e beleza* ➔ *Comércio e escritório*), sem risco de bloqueio por duplicidade.
- **Modo em Lote Sequencial (Sem Celular):** Republica Ventilador, Fone, Suporte McKenzie e Suporte XT Racer sequencialmente sem confirmações manuais, preservando automaticamente o limite restrito do celular (5/mês).

### Como Executar:
```powershell
cd olx

# Republicar TODOS os anúncios de cota abundante (Ventilador, Fone e Suportes - sem celular)
python republicar_tudo.py
# ou:
.\republicar_tudo.bat

# Simulação segura do lote da OLX
python republicar_tudo.py --dry-run

# Menu interativo individual (escolha Celular, Ventilador, Fone, McKenzie, XT Racer ou Verificar Cotas)
python republicar_anuncio.py

# Apenas consultar o saldo de cotas gratuitas
python republicar_anuncio.py --cotas
```

---

## 🛒 2. Facebook Marketplace (`marketplace/`)

Automação desenvolvida em **Playwright (Chromium)** conectada aos cookies da sessão do Firefox Nightly, com camada anti-detecção de bots e preenchimento de todos os campos avançados.

### Recursos:
- **Proteção Anti-Macro / Stealth:** Flags de evasão de webdriver, emulação de navegador real, atrasos randômicos e cadência de digitação realista.
- **Preenchimento Completo de Atributos:**
  - **Título, Preço e Fotos locais**
  - **Categoria e Condição** (*Usado — em boas condições* ou *Usado — estado de novo*)
  - **Marca e Seleção de Cor** em dropdown (*Branco* para o celular; *Galzerano* para o cercadinho)
  - **Etiquetas de Produto** (até 20 tags geradas dinamicamente)
  - **Preferências de Encontro:** *Encontro público* (celular e fone) ou *Retirada* (ventilador e cercadinho)
  - **Privacidade:** Ativação automática do switch *Ocultar para os amigos*
- **Exclusão Limpa:** Localiza o anúncio antigo em 'Seus classificados' e remove antes de republicar o novo.
- **Alternância Automática de Categorias:** Revezamento inteligente entre as categorias de maior conversão a cada republicação.
- **Modo em Lote Sequencial:** Executa os 5 itens ativos em sequência com intervalo de proteção anti-spam, sem solicitar confirmação manual.

### Como Executar:
```powershell
cd marketplace

# Republicar TODOS os 5 anúncios ativos em sequência (sem perguntas s/N)
python republicar_tudo.py
# ou:
.\republicar_tudo.bat

# Simulação segura dos itens ativos
python republicar_tudo.py --dry-run

# Republicar item individual via menu interativo (1 = Celular, 2 = Ventilador, 3 = Fone, 4 = McKenzie, 5 = XT Racer)
python republicar_marketplace.py
```

---

## 🛠️ Pré-requisitos e Dependências

- Python 3.10+
- Firefox Nightly instalado e logado nas contas da OLX e Facebook
- Pacotes Python:
```powershell
pip install cloudscraper requests playwright pillow
playwright install chromium
```
