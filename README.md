# ProvaSocial — Extract

Ferramenta forense de extração de evidências de redes sociais com cadeia de custódia
auditável, voltada para formação posterior de **Produção Antecipada de Provas (PAP)** e
pedidos de **quebra de sigilo / identificação de usuário**.

> Desenvolvido por **CyberMarmouts — Inteligência Forense**.

---

## O que a ferramenta entrega

Para uma URL de publicação/perfil de rede social, o sistema produz um **dossiê auditável**
focado na preservação do post:

- **Tripla captura**: HTML cru + screenshot full-page + PDF da página renderizada
- **Mídia**: download das imagens/vídeos do post
- **Comentários (auxiliar)**: tentativa best-effort quando visíveis/disponíveis (`comentarios.json` e `comentarios.txt`)
- **Metadados**: usuário (ID imutável), post (ID), data/hora, engajamento, etc.
- **Cadeia de custódia** (CPP art. 158-A): registro encadeado por hash de cada etapa
- **Carimbo de tempo**: UTC + Brasília (e, na versão hardening, RFC 3161)
- **Manifesto verificável**: SHA256 de todos os artefatos, encadeados
- **Laudo PDF** com QR code apontando para o portal público de verificação

## O que a ferramenta NÃO faz (importante)

Ela **não identifica** o nome/CPF/IP por trás de um perfil. Isso depende de **ordem
judicial** dirigida à plataforma (Marco Civil da Internet, arts. 22 e 23). A ferramenta
**prepara a prova auditável** que instrui esse pedido.

---

## Estrutura

```
Extract/
├── backend/
│   ├── config.py            # configurações (timezone, pastas, identidade do analista)
│   ├── captura/             # motores de captura por plataforma
│   │   ├── base.py
│   │   ├── comentarios.py   # comentários visíveis por DOM/Playwright
│   │   ├── http_capture.py  # HTML cru + headers + status (requests)
│   │   ├── render_capture.py# screenshot + PDF (Playwright)
│   │   └── metadados.py     # extração de metadados por plataforma
│   ├── custodia/            # núcleo de integridade
│   │   ├── hashing.py
│   │   ├── timestamp.py
│   │   ├── cadeia.py        # cadeia de custódia CPP 158-A
│   │   └── manifesto.py     # manifesto encadeado + verificação
│   ├── laudo/
│   │   └── gerar_pdf.py     # laudo HTML -> PDF (Playwright)
│   └── coletor.py           # orquestrador CLI
├── verificar.py             # verificador independente de integridade
├── evidencias/              # saída: uma pasta WORM por coleta (gerado em runtime)
├── static/if.png            # logo usado na interface e no laudo
├── requirements.txt
└── README.md
```

---

## Instalação

Requer **Python 3.10+**.

```bash
cd Extract
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt

# motor de render (screenshot/PDF) — baixa o Chromium headless
playwright install chromium
```

Para OCR do recorte do comentário alvo, instale também o Tesseract no sistema:

```bash
# Windows: instale pelo pacote UB Mannheim
# https://github.com/UB-Mannheim/tesseract/wiki

# Linux
sudo apt install tesseract-ocr tesseract-ocr-por
```

---

## Uso (CLI)

```bash
python -m backend.coletor \
  --url "https://x.com/exemplo/status/123456789" \
  --analista "CyberMarmouts - Inteligência Forense" \
  --caso "Caso02_BebeAlemao_Pomerode" \
  --evidencia "EV-001"
```

Busca direcionada de comentário alvo:

```bash
python -m backend.coletor \
  --url "https://www.instagram.com/p/..." \
  --comentario-alvo "trecho do comentário ofensivo"
```

Modo pericial/premium com gravação da navegação:

```bash
python -m backend.coletor \
  --url "https://www.instagram.com/p/..." \
  --comentario-alvo "trecho do comentário ofensivo" \
  --modo-pericial
```

Saída: `evidencias/EV-001_<codigo>/` com todos os artefatos + `laudo.pdf`.

### Verificar integridade de uma coleta

Qualquer terceiro (advogado, juiz, perito da parte contrária) pode rodar:

```bash
python verificar.py "evidencias/EV-001_<codigo>"
```

O verificador recalcula os hashes e confirma se o manifesto está **íntegro** ou
**adulterado**.

---

## Aplicação web SaaS (Fase 2)

Sobe o site completo (landing + login/registro + painel + pagamento Pix + portal de verificação):

```bash
uvicorn backend.api.app:app --reload
# acesse http://localhost:8000
```

### Modo simulado vs. produção

- **Sem `MP_ACCESS_TOKEN`** (padrão): roda em **MODO SIMULADO** — gera um Pix fictício e
  permite confirmar o pagamento manualmente (botão na tela). Ideal para desenvolvimento.
- **Com `MP_ACCESS_TOKEN`** (produção): integra com o Mercado Pago real (Pix). Configure:

```bash
# variáveis de ambiente
set MP_ACCESS_TOKEN=seu_token_de_producao
set PROVASOCIAL_BASE_URL=https://seudominio.com.br
set PROVASOCIAL_SECRET=uma_chave_longa_e_aleatoria
```

O webhook do Mercado Pago aponta para `POST /api/pagamentos/webhook` e só dispara a captura
após confirmar o status `approved` consultando a API (nunca confia só no payload recebido).

### Fluxo do usuário

1. Cria conta / faz login
2. Cola a URL do post/perfil → gera o Pix (R$ 9,90)
3. Paga (ou confirma no modo simulado) → a captura inicia em background
4. Acompanha o status no painel → baixa o laudo + artefatos
5. Qualquer terceiro verifica em `/verificar/<codigo>`

## Roadmap (fases)

1. **Núcleo** (entregue): captura + custódia + laudo + verificação local — X e genérico
2. **Monetização** (entregue): site + auth + Mercado Pago (Pix) + webhook + painel + portal
3. **Multi-plataforma** (entregue): extratores X/Instagram/Facebook/TikTok/YouTube, oEmbed,
   download de todas as mídias, análise EXIF/GPS (ExifTool + fallback Pillow), timestamps
4. **Produtos complementares** (entregue): identifica limitações de Instagram/Facebook,
   oferece Instruções à PAP Seu Custódio, Consultoria Técnica Jurídica Individual e reforço notarial
5. **Hardening**: WORM/Object Lock, RFC 3161, proxies/anti-bloqueio, LGPD, anti-abuso, fila Celery/Redis

## Produtos complementares

Quando a coleta pública não obtém identificador numérico interno (especialmente
Instagram/Facebook), o laudo registra essa limitação de forma defensável e a interface
oferece produtos complementares CyberMarmouts:

- **Instruções à PAP Seu Custódio**: organização inicial dos dados, contexto e artefatos para apoiar a preparação de Produção Antecipada de Provas;
- **Consultoria Técnica Jurídica Individual**: análise humana do caso, priorização de elementos técnicos, estratégia de identificação e encaminhamentos;
- pedido de quebra de sigilo;
- eventual reforço por ata notarial.

As Instruções à PAP não substituem advogado, petição judicial ou parecer pericial conclusivo. Elas funcionam como produto plus entre a captura automatizada e a consultoria individual.

## Captura autenticada do operador

Para Instagram/Facebook, a captura pública pode ficar atrás do banner de login. O modo
autenticado permite usar uma sessão logada do operador CyberMarmouts no Playwright.

### 1. Gerar a sessão logada

```bash
python -m backend.sessao_operador --plataforma instagram
```

Uma janela do Chromium será aberta. Faça login manualmente, resolva 2FA/captcha se houver
e pressione ENTER no terminal. A sessão será salva em:

```text
sessoes/operador.json
```

Para Facebook:

```bash
python -m backend.sessao_operador --plataforma facebook
```

### 2. Rodar a captura normalmente

```bash
uvicorn backend.api.app:app --reload
```

Se `sessoes/operador.json` existir, o render Playwright usará essa sessão automaticamente.
O laudo/metadados indicam `captura_autenticada = sim` e registram apenas o hash da sessão.

### Segurança da sessão

O arquivo `sessoes/operador.json` contém cookies/tokens. Ele:

- não é versionado (`.gitignore`);
- não é anexado ao laudo;
- não deve ser enviado ao cliente;
- deve ser tratado como segredo operacional.

## Comentários (recurso auxiliar)

O produto principal é a **captura auditável da publicação**. O sistema também tenta
coletar comentários visíveis durante a renderização, mas isso não é vendido como
garantia principal:

- clica em botões como "Ver mais comentários", "Ver respostas" e equivalentes em inglês;
- faz scroll progressivo;
- permite informar um **comentário alvo** para busca direcionada com scroll mais profundo;
- salva `comentarios.json` (estruturado) e `comentarios.txt` (leitura rápida);
- quando o comentário alvo é encontrado, salva `comentario_alvo.json`, recorte visual (`comentario_alvo_screenshot.png`) e DOM do elemento (`comentario_alvo_dom.html`);
- tenta OCR opcional do recorte se `pytesseract` e o Tesseract estiverem instalados;
- inclui um resumo no laudo;
- registra status como `coletado`, `bloqueado_por_login`, `nao_encontrado` ou `erro`.

Por limitação das plataformas, essa coleta é **best-effort**: comentários ocultos,
apagados, paginados, bloqueados por login ou indisponíveis no momento da captura podem
exigir sessão autenticada, assessoria ou requisição judicial à plataforma.

### Busca por comentário alvo

Use quando a agressão está em um comentário específico:

```bash
python -m backend.coletor --url "https://www.instagram.com/p/..." --comentario-alvo "trecho do comentário ofensivo"
```

Para a camada pericial/premium, habilite também a gravação da navegação Playwright:

```bash
python -m backend.coletor --url "https://www.instagram.com/p/..." --comentario-alvo "trecho do comentário ofensivo" --modo-pericial
```

O OCR não substitui o carregamento da página: ele só lê aquilo que apareceu no recorte visual. A estratégia do MVP é **DOM + scroll direcionado + screenshot focado**; a estratégia pericial adiciona **vídeo da navegação + OCR opcional + DOM preservado**.

## Rede corporativa / proxy (verificação SSL)

A verificação de certificado SSL fica **ligada por padrão** (essencial para a integridade
forense). Em redes com proxy que faz inspeção TLS, aponte o CA bundle da empresa:

```bash
set PROVASOCIAL_CA_BUNDLE=C:\caminho\para\ca-corporativo.pem
```

Evite desligar a verificação; se for estritamente necessário em ambiente de teste:
`set PROVASOCIAL_VERIFICAR_SSL=0`.

---

## Avisos legais (LGPD / uso responsável)

- O uso deve observar a LGPD e destinar-se ao **exercício regular de direitos** (processo
  judicial/administrativo). O solicitante é responsável pelo uso.
- A captura é feita **no servidor**, de forma independente, para garantir credibilidade
  probatória — o conteúdo não é fornecido pelo solicitante.
