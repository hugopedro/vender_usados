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
│   ├── republicar_anuncio.py            # Automação via API direta da OLX + Gestão de Cotas
│   ├── historico_cotas.json             # Histórico e saldo de cotas de anúncios gratuitos
│   └── ESTRATEGIA_REPUBLICACAO_OUTUBRO_2026.md # Planejamento estratégico de reupagem
│
├── marketplace/
│   ├── celular/                         # Metadados, fotos e tags do celular
│   ├── ventilador/                      # Metadados, fotos e tags do ventilador
│   ├── fone/                            # Metadados, fotos e tags do fone
│   ├── memoria/                         # Metadados, foto e tags da Memória RAM Kingston 8GB DDR4
│   └── republicar_marketplace.py        # Automação via Playwright Chromium + Stealth
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
- **Modo Verificação de Cotas:** Relatório completo sem alterar nada.

### Como Executar:
```powershell
cd olx

# Menu interativo (escolha Celular, Ventilador, Fone ou Verificar Cotas)
python republicar_anuncio.py

# Apenas consultar o saldo de cotas gratuitas
python republicar_anuncio.py --cotas

# Simulação segura (não exclui nem publica)
python republicar_anuncio.py 1 --dry-run
```

---

## 🛒 2. Facebook Marketplace (`marketplace/`)

Automação desenvolvida em **Playwright (Chromium)** conectada aos cookies da sessão do Firefox Nightly, com camada anti-detecção de bots e preenchimento de todos os campos avançados.

### Recursos:
- **Proteção Anti-Macro / Stealth:** Flags de evasão de webdriver, emulação de navegador real, atrasos randômicos e cadência de digitação realista.
- **Preenchimento Completo de Atributos:**
  - **Título, Preço e Fotos locais**
  - **Categoria e Condição** (*Usado — em boas condições* ou *Usado — estado de novo*)
  - **Marca e Seleção de Cor** em dropdown (*Branco* para o celular; *Kingston* para a memória)
  - **Etiquetas de Produto** (até 20 tags geradas dinamicamente)
  - **Preferências de Encontro:** *Encontro público* (celular, fone, memória) ou *Retirada* (ventilador)
  - **Privacidade:** Ativação automática do switch *Ocultar para os amigos*
- **Exclusão Limpa:** Localiza o anúncio antigo em 'Seus classificados' e remove antes de republicar o novo.

### Como Executar:
```powershell
cd marketplace

# Menu interativo (1 = Celular, 2 = Ventilador, 3 = Fone, 4 = Memória RAM)
python republicar_marketplace.py

# Simulação segura
python republicar_marketplace.py 4 --dry-run
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
