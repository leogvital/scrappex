# X Video Scraper

*[Read in English](README.md)*

Aplicação web local para buscar e baixar vídeos do **X (Twitter)**, **XHamster**, **XVideos**, **xFree** e **Pornhub**.

> Veja o [ROADMAP.md](ROADMAP.md) para o que já foi feito e os próximos passos planejados.

## Visão Geral da Arquitetura

```
scrapperx/
├── app.py               # Backend Flask (API REST)
├── index.html           # Frontend React (SPA, sem build)
├── setup.sh             # Linux/Mac — instala dependências
├── start.sh             # Linux/Mac — inicia o servidor (foreground, Gunicorn)
├── restart.sh           # Linux/Mac — reinicia em background, com log
├── setup_windows.bat    # Windows — instala dependências
├── start_windows.bat    # Windows — inicia o servidor (foreground, Waitress)
├── restart_windows.bat  # Windows — reinicia em background, com log
└── venv/                # Ambiente virtual Python
```

O backend serve tanto a API (`/api/*`) quanto o frontend (`/`), no mesmo processo — sem servidor separado.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Servidor | Flask 3 + Gunicorn (1 worker, `gthread`, 4 threads, timeout 600 s) — **Linux/Mac**. No **Windows**, Gunicorn não roda (usa `fork()`, que não existe lá); usa-se Waitress no lugar, com `--threads 4` pelo mesmo motivo |
| Scraping X e xFree | Selenium + Chrome headless (WebDriver Manager) |
| Scraping XHamster/XVideos/Pornhub | `requests` (HTTP direto) |
| Download de vídeos | yt-dlp |
| Frontend | React 18 + Babel standalone (zero build step) |
| Armazenamento de cookies | Arquivo Netscape em `/tmp/x_cookies.txt` |
| Vídeos baixados | `~/Downloads/X-Videos/` |

**Por quê `gthread` + `--threads 4`**: o worker `sync` padrão do Gunicorn processa **uma requisição por vez** — enquanto uma busca lenta (Selenium fazendo scroll no X/xFree, por exemplo) está em andamento, nenhuma outra requisição é sequer aceita, incluindo `/api/download/start`. Era exatamente isso que travava o download quando clicado durante o carregamento automático de mais vídeos. `gthread` mantém um único processo (preservando o estado global em memória — `_SS`, `_XF_SS`, `_SITE_SS`, `download_progress` — que não é compartilhável entre processos sem um store externo tipo Redis) mas processa até 4 requisições em paralelo dentro dele, já que a maior parte do trabalho aqui é I/O (esperar o Selenium, esperar respostas HTTP) e libera o GIL nesses momentos.

---

## Instalação e Execução

Escolha a seção do seu sistema operacional. Os dois usam os mesmos `app.py`/`index.html` — só os scripts de setup/start mudam.

### 🐧 Linux (Ubuntu/Debian) — passo a passo

**1. Pré-requisitos:**
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# Google Chrome (necessário para o scraping via Selenium — X e xFree)
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable
```

**2. Baixar o projeto** (se ainda não tiver a pasta `scrapperx/`):
```bash
git clone https://github.com/leogvital/scrappex.git scrapperx
cd scrapperx
```

**3. Instalar dependências** (cria o `venv/` e instala tudo dentro dele — não mexe no Python do sistema):
```bash
bash setup.sh
```

**4. Configurar o login do app** (veja a seção [Login do App](#login-do-app) abaixo):
```bash
cp .env.local.example .env.local
# edite .env.local e defina SCRAPPERX_APP_USER / SCRAPPERX_APP_PASS
```

**5. Iniciar:**
```bash
# Em primeiro plano (fica preso no terminal, Ctrl+C para parar) — bom para ver logs/depurar
bash start.sh

# OU em segundo plano (continua rodando mesmo fechando o terminal) — bom para uso do dia a dia
bash restart.sh
# Logs: tail -f /tmp/scrapperx.log
```

**6. Acessar**: [http://localhost:5000](http://localhost:5000)

**Requisitos:**
- Python 3.10+
- Google Chrome instalado (para scraping do X e xFree via Selenium)
- `python3-venv` (incluso no passo 1 acima)

---

### 🪟 Windows — passo a passo

**1. Instalar o Python:**
- Baixe em [python.org/downloads](https://www.python.org/downloads/) (3.10 ou mais recente)
- Na tela de instalação, marque **"Add python.exe to PATH"** antes de clicar em Instalar — esse passo é fácil de esquecer e sem ele os scripts `.bat` não encontram o Python
- Confirme abrindo o **Prompt de Comando** (`cmd`) e rodando `python --version`

**2. Instalar o Google Chrome:**
- Baixe e instale em [google.com/chrome](https://www.google.com/chrome/) (necessário para o scraping do X e xFree via Selenium — o `webdriver-manager` baixa o `chromedriver` compatível automaticamente, só precisa do Chrome instalado)

**3. Baixar o projeto** (se ainda não tiver a pasta `scrapperx/`):
- Via Git: `git clone https://github.com/leogvital/scrappex.git scrapperx`
- Ou baixe o `.zip` do repositório e extraia numa pasta

**4. Instalar dependências** — abra o **Prompt de Comando** dentro da pasta `scrapperx` (clique na barra de endereço do Explorer, digite `cmd` e Enter) e rode:
```bat
setup_windows.bat
```
Isso cria o `venv\` e instala tudo dentro dele (não mexe no Python do sistema).

**5. Configurar o login do app** (veja a seção [Login do App](#login-do-app) abaixo) — copie `.env.local.example` para `.env.local` e edite os valores de `SCRAPPERX_APP_USER`/`SCRAPPERX_APP_PASS` num editor de texto.

**6. Iniciar:**
```bat
REM Em primeiro plano (fica preso na janela, feche-a para parar) — bom para ver logs/depurar
start_windows.bat

REM OU em segundo plano (continua rodando mesmo fechando este terminal) — bom para uso do dia a dia
restart_windows.bat
REM Logs: %TEMP%\scrapperx.log
```

**7. Acessar**: [http://localhost:5000](http://localhost:5000)

**Requisitos:**
- Python 3.10+ com "Add to PATH" marcado na instalação
- Google Chrome instalado
- Windows 10/11 (os `.bat` usam `netstat`/`taskkill`/PowerShell embutidos, sem instalar nada extra)

**Diferenças do Linux**: no Windows o servidor roda via **Waitress** em vez de **Gunicorn** (Gunicorn depende de `fork()`, que não existe no Windows) — mesma ideia, resultado equivalente. A extração automática de cookies do Chrome/Edge também funciona diferente por baixo dos panos (Windows usa DPAPI para descriptografar; Linux usa uma chave fixa ou o keyring via `secretstorage`), mas isso já é tratado automaticamente pelo `yt-dlp` como fallback — não precisa fazer nada extra.

> **Alternativa**: se preferir rodar exatamente os mesmos comandos do Linux num Windows, instale o **WSL2** (`wsl --install` no PowerShell como administrador) com Ubuntu, e siga a seção 🐧 Linux acima de dentro do WSL.

**Nota sobre `--no-control-socket`**: `start.sh`/`restart.sh` passam essa flag ao Gunicorn 26+ para desativar o *control socket* (feature administrativa usada só pelo `gunicornc`, que este projeto não usa). Sem ela, o Gunicorn tenta criar `$XDG_RUNTIME_DIR/gunicorn.ctl` — se essa variável tiver vazado de uma sessão root anterior (comum ao trocar de usuário com `su usuario -c '...'` sem o `-`, ou `sudo -u usuario` sem resetar o ambiente), ele tenta escrever em `/run/user/0/` e falha com `PermissionError`. O servidor HTTP em si sobe normalmente mesmo com esse erro (é só o socket de controle que falha), mas `--no-control-socket` elimina a classe inteira do problema.

---

## Login do App

Todo o app fica atrás de uma tela de login própria (independente dos cookies do X abaixo), com usuário e senha configurados via variável de ambiente — **não** ficam no código-fonte (o repositório é público):

```bash
# 1. Copie o template
cp .env.local.example .env.local

# 2. Edite .env.local e defina:
SCRAPPERX_APP_USER=admin
SCRAPPERX_APP_PASS=sua-senha-aqui
```

`.env.local` está no `.gitignore` — fica só na sua máquina/servidor, `start.sh`/`restart.sh` (e os `.bat` no Windows) carregam essas variáveis automaticamente antes de subir o servidor. Sem `.env.local` (ou sem `SCRAPPERX_APP_PASS` definida), o login fica bloqueado para todo mundo — o backend avisa isso no log ao iniciar.

- Backend (`app.py`): `before_request` bloqueia qualquer rota `/api/*` (exceto `/api/auth/app-login`, `/api/auth/app-status` e `/api/health`) enquanto `session["app_logged_in"]` não estiver setado.
- **Sessão persistente**: `app.secret_key` é gerado uma vez e salvo em `.flask_secret_key` (permissão `600`) — carregado desse arquivo em todo start subsequente, então reiniciar o servidor **não** derruba quem já estava logado. No login, `session.permanent = True` + `PERMANENT_SESSION_LIFETIME = 30 dias` fazem o cookie sobreviver a fechar o navegador (sem isso seria um cookie de sessão, apagado ao fechar). Se `.flask_secret_key` for recriado por outro usuário do sistema (dono diferente do processo do servidor), o load falha com `PermissionError` no boot — apague o arquivo para o processo atual recriá-lo com o dono certo.
- **Login do X também sobrevive a restart**: no boot, se `x_cookies.txt` já existir, o backend roda `validate_cookies()` automaticamente e repõe `session_state["logged_in"]` — sem isso, mesmo com os cookies do X intactos em disco, o restart forçava a tela de auth do X de novo a cada reinício.
- Endpoints: `POST /api/auth/app-login`, `POST /api/auth/app-logout`, `GET /api/auth/app-status`.
- Frontend (`index.html`): `Root` faz o gate antes de renderizar `App` — mostra `AppLoginScreen` se não autenticado, senão renderiza `App` com um botão flutuante "🔒 Sair" no canto inferior esquerdo.

---

## Autenticação

O acesso ao X requer cookies de sessão válidos. Três métodos disponíveis:

### 1. Auto-detecção (recomendado para Linux)
Detecta e importa cookies diretamente do banco SQLite do Chrome, Firefox ou Edge.
- Chrome no Linux não criptografa cookies por padrão
- Fallback automático via yt-dlp se a leitura direta falhar

### 2. Via yt-dlp
Usa o extrator nativo do yt-dlp, que lida com criptografia do keyring do sistema.
Suporta: Chrome, Firefox, Edge, Opera, Brave.
> Feche o navegador antes de usar este método.

### 3. Colar cookies manualmente
Cole o JSON exportado pela extensão [Cookie-Editor](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) ou texto no formato Netscape.

Após importar, os cookies são validados via `POST` de uma `media/upload.json` INIT (`total_bytes=1`) — o mesmo endpoint que a publicação de tweet usa de verdade.

> **Nota histórica**: até 2026-08, a validação usava `GET /i/api/1.1/account/verify_credentials.json`. Esse endpoint passou a devolver sempre `404 {"message":"Sorry, that page does not exist","code":34}` — inclusive para cookies genuinamente válidos (confirmado: as mesmas cookies funcionavam normalmente em `media/upload.json` INIT). Ou seja, não é mais um sinal confiável de sessão expirada, é o endpoint em si que a X descontinuou para esse tipo de autenticação. Isso causava logout falso: `session_state["logged_in"]` ficava preso em `False` (ou, pior, preso em `True` de antes — `/api/auth/validate` só *ligava* a flag em sucesso, nunca *desligava* em falha) mesmo com cookies funcionais, e o usuário via erros crus da API do X (`"Failed to authenticate. API Error: 401 OAuth access token has expired."`) em vez da tela de reautenticação. Trocar o endpoint de prova resolveu ambos.

---

## Funcionalidades de Busca

### X (Twitter) — via Selenium
| Modo | Descrição |
|---|---|
| Para Você | Feed principal (`/home`) — inicia automaticamente ao clicar na aba |
| Seguindo | Feed "Seguindo" (clica na aba via Selenium) — inicia automaticamente |
| Palavra-chave | Busca com `filter:videos` |
| Hashtag | Página de hashtag com filtro de vídeos |
| Usuário | Aba `/media` do perfil |

O Selenium mantém **uma sessão Chrome persistente** entre paginações — o driver não é reiniciado a cada "Carregar mais", evitando re-scroll e duplicatas. A sessão expira após 600 s de inatividade ou 60 scrolls.

**Auto-scroll infinito:** ao chegar a 700 px do final da página, novos resultados são carregados automaticamente (sem clicar em botão), simulando a navegação nativa do X.

### XHamster e XVideos — via HTTP
Scraping direto da página HTML, sem navegador headless. Duas abas — Home e Busca — mais categoria de orientação (❤️ Heterossexual / 🏳️‍🌈 Gay / 🏳️‍⚧️ Trans), no mesmo esquema simples de prefixo de URL nos dois sites:

| Categoria | Prefixo (XHamster e XVideos) |
|---|---|
| ❤️ Heterossexual | *(nenhum)* |
| 🏳️‍🌈 Gay | `/gay` |
| 🏳️‍⚧️ Trans | `/shemale` |

- **XHamster**: tanto a Home (`{prefixo}?page=N`) quanto a Busca (`{prefixo}/search/{query}?page=N`) usam o mesmo blob JSON embutido (`window.initials`) — a Busca guarda os itens em `searchResult.videoThumbProps`, a Home em `layoutPage.videoListProps.videoThumbProps`. `_scrape_xhamster` tenta os dois caminhos.
- **XVideos**: a Busca (`{prefixo}/?k=...&p=N`) pagina normalmente, mas a **Home não pagina** — `{prefixo}/` devolve sempre o mesmo destaque independente de `page`/`p` (confirmado testando direto via HTTP, fora do app). Por isso a Home do XVideos sempre tem `has_more=false` — sem "carregar mais" — e a UI mostra um aviso disso.
- Ordenação (só na Busca): relevância, mais novos, visualizações, melhor avaliado, mais longos
- Filtro de duração (lado cliente): curto (<10 min), médio (10–30 min), longo (>30 min)

### xFree — Selenium (home e busca)
Scraping do xfree.com (Vue.js/Nuxt SSR) via Chrome headless, para Home e Busca.

- **Por quê Selenium para tudo**: nem a Home nem a Busca do xfree.com paginam de forma confiável via HTTP simples — o conteúdo é carregado via infinite scroll client-side, chamando um endpoint JSON interno (`/api/2/search?...&offset=N`) protegido por Cloudflare que bloqueia requisições HTTP diretas (404). As categorias Gay/Trans (`/gay`, `/trans`) além disso são bloqueadas por um challenge do Cloudflare específico para bots que só um navegador real consegue passar. Por isso tudo — Home e Busca, nas 4 categorias — abre uma sessão Chrome headless (`_XF_SS`, análoga à `_SS` do X) e simula scroll (`_xf_scroll_down`) até acumular `page_size` itens novos, com dedup por ID (`seen_ids`).
- **Categoria (Hétero / Gay / Trans / Tudo)**: a categoria é estado do Vuex do site (não um query param), definido por navegação real para sua rota dedicada — `/`, `/gay`, `/trans`, `/all`. Por isso a sessão sempre começa com `driver.get()` na rota da categoria escolhida; para busca, a query é digitada no campo de busca da própria página (`input[name=q]`) e enviada com Enter, preservando o estado de categoria já carregado (navegar direto para uma URL `/search?q=...` reseta esse estado para "Hétero").
- Os links de vídeo carregam um sufixo por categoria — `/video?id=` (hétero/tudo), `/video-gay?id=`, `/video-trans?id=` — preservado pelo parser (`_parse_xfree_blocks`) para manter a URL de reprodução correta.
- Sem suporte a ordenação server-side (ordenação é client-side no Vue.js)

### Pornhub (pt.pornhub.com) — via HTTP
Scraping direto da página HTML, sem navegador headless (`_scrape_pornhub`). Duas abas — Home e Busca — mais categoria de orientação:

| Categoria | Vertical do site (Home) | Busca por palavra-chave |
|---|---|---|
| ❤️ Heterossexual | `/` | `/video/search?search=...` |
| 🏳️‍🌈 Gay | `/gayporn` | `/gay/video/search?search=...` |
| 🏳️‍🌈 Sáfica | `/lesbian` | `/lesbian/video/search?search=...` |
| 🏳️‍⚧️ Trans | `/transgender` | **sem endpoint dedicado** |

- **Home** não requer query — carrega os vídeos em destaque da vertical da categoria selecionada (mesma URL usada como fallback de busca do Trans).
- Gay e Sáfica são "verticais" próprias do site (mesmo domínio, HTML SSR já filtrado pela orientação) com endpoint de busca dedicado — funcionam via HTTP simples, sem bloqueio.
- Trans não tem endpoint de busca por palavra-chave no site — a categoria browsa o feed de destaque de `/transgender` tanto na Home quanto na Busca, e **ignora o texto digitado** na Busca, avisando o usuário na UI (mensagem informativa quando "Trans" é selecionado).
- Paginação via `?page=N`, igual para todas as categorias e para Home/Busca.
- **Dedup entre páginas**: a paginação por categoria do Pornhub repete alguns itens promovidos entre páginas consecutivas (confirmado direto via HTTP, fora do app). Por isso `_SITE_SS` (usado também por XHamster/XVideos) ganhou um `seen_ids` que filtra IDs já vistos antes de devolver cada página.
- **Thumbnail**: os cards da Home/trending usam um atributo diferente (`data-mediumthumb`) dos cards de busca (`data-image`) — `_scrape_pornhub` tenta os dois antes de cair para o `src` puro da `<img>`, senão vários previews ficavam em branco na Home.

---

## API REST

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/auth/app-login` | Login do app (usuário/senha fixos) |
| POST | `/api/auth/app-logout` | Logout do app |
| GET | `/api/auth/app-status` | Estado da sessão de login do app |
| GET | `/api/session` | Estado da sessão atual (requer login do app) |
| POST | `/api/auth/auto-import` | Importar cookies do navegador |
| POST | `/api/auth/yt-dlp-browser` | Importar cookies via yt-dlp |
| POST | `/api/auth/paste-cookies` | Importar cookies colados |
| POST | `/api/auth/validate` | Validar cookies ativos |
| POST | `/api/upload/init` | Inicia upload chunked (Twitter INIT) |
| POST | `/api/upload/chunk` | Envia segmento de 5 MB (Twitter APPEND) |
| POST | `/api/upload/finalize` | Finaliza upload e aguarda processamento |
| POST | `/api/tweet/create` | Publica tweet com texto e/ou vídeo |
| POST | `/api/auth/logout` | Encerrar sessão e apagar cookies |
| POST | `/api/search` | Buscar vídeos (primeira página) |
| POST | `/api/search/more` | Carregar próxima página |
| POST | `/api/preview` | URL direta para preview no navegador |
| POST | `/api/formats` | Listar formatos disponíveis (yt-dlp) |
| POST | `/api/download/start` | Iniciar download assíncrono |
| GET | `/api/download/progress/<tid>` | Progresso do download |
| GET | `/api/download/file/<tid>` | Servir arquivo baixado |
| GET | `/api/library` | Listar vídeos na pasta de downloads |
| GET | `/api/library/video/<name>` | Servir vídeo da biblioteca (streaming) |
| POST | `/api/library/delete` | Excluir vídeo da biblioteca |

---

## Frontend (React SPA)

Toda a interface está em `index.html` como JSX inline compilado pelo Babel no navegador — sem `npm build`. Componentes principais:

| Componente | Função |
|---|---|
| `Root` | Gate de login do app — decide entre `AppLoginScreen` e `App` |
| `AppLoginScreen` | Tela de login do app (usuário/senha fixos) |
| `AuthScreen` | Tela de login com as 3 abas de importação de cookies do X |
| `VideoCard` | Card de resultado com preview embutido e checkbox de seleção |
| `FormatModal` | Modal de seleção de qualidade e progresso de download |
| `BulkActionBar` | Barra fixa de download em lote (seleção múltipla) |
| `BulkProgressModal` | Modal com progresso simultâneo de vários downloads |
| `BgTray` | Pill flutuante de downloads em background |
| `PostModal` | Modal para compor e publicar tweet com vídeo (upload chunked com progresso real) |
| `LibraryGrid` | Grid de vídeos baixados |
| `PlayerModal` | Player fullscreen com seek, play/pause, próximo/anterior, exclusão |

### Histórico e favoritos de busca

Toda busca bem-sucedida (qualquer plataforma, incluindo carregamentos da Home) é registrada em `searchHistory`, persistida em `localStorage` sob `scrapperx_search_history` — o mesmo padrão já usado pro rastreio de downloads em background (`scrapperx_bg_tasks`). Uma entrada do histórico é identificada por `platform+type+query+category`; repetir a mesma busca move ela pro topo em vez de duplicar, e preserva uma marcação de favorito existente em vez de substituí-la por uma entrada nova sem estrela. Entradas não-favoritas são limitadas a `HISTORY_MAX` (30, as mais antigas caem primeiro); favoritas ficam isentas do limite e de "Limpar histórico" (que só apaga entradas não-favoritas).

Clicar numa entrada do histórico (`runHistoryEntry`) precisa tanto atualizar os seletores visíveis de plataforma/tipo/query/categoria quanto disparar a busca na hora — mas setters de estado do React são assíncronos, então `search()` lendo `platform`/`query`/etc. do seu próprio closure ainda veria os valores *anteriores* nessa mesma chamada. Por isso `search()` aceita um objeto `overrides` opcional que tem prioridade sobre o estado atual só nessa invocação, enquanto todo chamador existente (o botão de busca, o `Enter` no campo de query, o efeito de auto-busca na troca de aba) continua chamando `search()` sem argumentos e se comporta exatamente como antes. Uma consequência que vale saber se for mexer nesse código: `search` é chamado diretamente como `onClick={()=>search()}`, nunca cru como `onClick={search}` — o React passaria o `SyntheticEvent` do clique como `overrides` nesse caso, e como eventos carregam uma propriedade `.type` de verdade (`"click"`), `eType` silenciosamente viraria a string `"click"` em vez de cair pro estado.

Validado com um teste de render headless (jsdom + React 18, transformando via Babel o próprio bloco de script do `index.html`) simulando cliques e eventos de input reais de ponta a ponta: abrir o painel de histórico vazio, rodar uma busca e confirmar que ela foi registrada com o rótulo certo, favoritar uma entrada, confirmar que "Limpar histórico" a preserva, e confirmar que clicar numa entrada do histórico dispara um `/api/search` novo com o corpo esperado.

---

## Download de Vídeos

- **Download único**: seleciona formato específico (qualidade, codec, tamanho estimado) via yt-dlp
- **Download em lote**: inicia todos em paralelo, exibe progresso individual
- **Background**: ao fechar o modal durante o download, o task continua e aparece no `BgTray`
- **Sobrevive a fechar o navegador**: o download roda numa `threading.Thread` no processo do servidor (`download_task` em `app.py`), completamente desacoplada da conexão HTTP — fechar a aba/navegador não interrompe o download. O que faltava era o *frontend* lembrar quais tasks estavam em andamento: `bgRef`/`bgTasks` agora são espelhados em `localStorage` (`scrapperx_bg_tasks`) a cada atualização de progresso, e um `useEffect` no mount do `App` relê essa lista e retoma o polling — reabrir o navegador reconecta ao progresso real. Se o *servidor* reiniciar no meio do download (não só o navegador), o progresso em memória (`download_progress`) se perde; a UI detecta isso (resposta `not_found`) e marca a task como erro em vez de travar tentando para sempre.
- Formatos suportados: `best`, até 1080p, até 720p, até 480p
- Saída: `~/Downloads/X-Videos/<título>_<id>.mp4`

### Pornhub precisa de impersonation de TLS
O extrator nativo do yt-dlp para Pornhub leva `403 Forbidden` ao baixar a página do vídeo — é um bloqueio por *fingerprint* de TLS (JA3/JA4), não por headers HTTP (confirmado: os mesmos headers via `requests` puro funcionam normalmente, só a stack de rede do yt-dlp é bloqueada). A correção é fazer o yt-dlp imitar o handshake TLS de um Chrome real via `curl_cffi`:
- `setup.sh` instala `curl_cffi` (fixado em `>=0.10,<0.15` — a v0.15 quebra a API que o yt-dlp `2026.03.17` espera)
- `build_ydl_opts(extra, url)` detecta URLs de `pornhub.com` e injeta `impersonate=ImpersonateTarget.from_str("chrome")` (a API Python do yt-dlp exige o objeto `ImpersonateTarget`, diferente do `--impersonate chrome` da CLI que aceita string)
- Aplica-se a `/api/formats`, `/api/download/start` e `/api/preview`

---

## Fluxo de Sessão Selenium

```
POST /api/search
  └─ _ss_close()           # encerra sessão anterior
  └─ _ss_driver()          # cria Chrome headless
  └─ _ss_inject_cookies()  # injeta cookies via CDP
  └─ navega para a URL
  └─ _ss_fetch_page()      # parseia artigos visíveis, scrolla se necessário
  └─ armazena driver em _SS{}

POST /api/search/more
  └─ verifica _SS["id"] e timeout
  └─ _ss_fetch_page()      # continua de onde parou
```

A Home e a Busca do xFree usam o mesmo padrão de sessão (sem cookies, sem X):

```
POST /api/search  (platform=xfree, category=straight|gay|trans|all)
  └─ _xf_close()           # encerra sessão anterior
  └─ _ss_driver()          # cria Chrome headless (reaproveitado do X)
  └─ navega para /, /gay, /trans ou /all      # define a categoria (estado Vuex)
  └─ se houver query: digita no input[name=q] da própria página e envia Enter
  └─ _xf_fetch_page()      # parseia wall__item visíveis, scrolla se necessário
  └─ armazena driver em _XF_SS{}

POST /api/search/more
  └─ verifica _XF_SS["id"] e timeout
  └─ _xf_fetch_page()      # continua de onde parou
```

A sessão é encerrada automaticamente pelo `atexit` quando o servidor para.

### Limpeza robusta de processos travados (`_hard_kill_driver`)

Quando o Chrome/chromedriver de uma sessão crasha sozinho (`tab crashed`, `Connection refused` no `_ss_fetch_page`/`_xf_fetch_page`), `driver.quit()` não adianta — ele precisa de uma conexão WebDriver funcionando pra pedir ao Chrome que feche, e é exatamente essa conexão que está quebrada. Sem tratamento, a árvore inteira de processos (chromedriver + Chrome + zygote/gpu/renderer) fica órfã rodando pra sempre — **~1-1.5 GB de RAM por sessão travada** (foi encontrada uma sessão órfã de ~15h consumindo a memória do servidor até quase estourar o swap).

`_ss_close()`/`_xf_close()` agora chamam `_hard_kill_driver()`, que:
1. Tenta `driver.quit()` normalmente (melhor esforço)
2. Mata o processo do chromedriver direto por PID (`drv.service.process.pid`)
3. Varre **todos** os processos do sistema procurando o `--user-data-dir` único daquela sessão (tag salva em `drv._user_data_dir` na criação, em `_ss_driver()`) e mata qualquer processo cujo cmdline contenha esse caminho

O passo 3 existe porque testar um walk pai→filho (`psutil.Process(pid).children()`) **não funciona** quando o chromedriver já está morto: os processos filhos são reparentados imediatamente (para fora da árvore do chromedriver morto), então perguntar "quais são os filhos desse PID" depois do crash não encontra nada — confirmado simulando o crash e testando (0 de 9 processos órfãos mortos com o walk; 9 de 9 mortos com a varredura por `--user-data-dir`). Não usa `killpg` — o chromedriver compartilha o grupo de processos do próprio Gunicorn, e matar o grupo derrubaria o servidor junto.

### Retry automático em crashes transientes do navegador

Os mesmos erros `tab crashed`/`Connection refused` acima não só vazam processos — sem retry, eles também aparecem como uma exceção Python crua direto pro usuário, no meio do que quer que ele estivesse fazendo quando o Chrome morreu. `_x_open_session()`/`_xf_open_session()` (X e xFree respectivamente) extraem o fluxo de "criar uma sessão do Chrome, logar / escolher categoria, esperar o conteúdo" pra fora dos route handlers, pra poder ser reaproveitado por:

- **Uma busca nova** (`/api/search`): envolvida num loop de até `_BROWSER_RETRY_ATTEMPTS` (2) tentativas — numa falha transiente, a sessão morta é limpa (`_ss_close()`/`_xf_close()`, que agora também roda `_hard_kill_driver()`) e o fluxo inteiro tenta de novo do zero com uma instância nova do Chrome.
- **"Carregar mais"** (`/api/search/more`): um crash no meio do scroll não dá pra simplesmente repetir a mesma chamada (o driver já era), então em vez disso a sessão é **reaberta** pra mesma busca (mesma URL/tipo pro X; mesma categoria/query pro xFree) e retomada — `seen_ids` e `scroll_count` são levados pra sessão nova antes, então a busca retomada naturalmente pula tudo que já foi mostrado em vez de devolver duplicatas.

`_is_transient_browser_error()` compara a mensagem da exceção com assinaturas de crash conhecidas (`connection refused`, `tab crashed`, `errno 5`, `invalid session id`, etc.) — só essas são retentadas; um `TimeoutException` do Selenium genuinamente não encontrando resultados (ou a X pedindo login de novo) levanta `_NoResultsError` em vez disso e nunca é retentado, já que tentar de novo não mudaria esse resultado. Validado simulando `_xf_open_session`/`_x_open_session`/`_ss_fetch_page`/`_xf_fetch_page` falhando uma vez com as strings de erro exatas vistas em produção, confirmando: o retry dispara exatamente uma vez, erros não-transientes falham na hora sem tentar de novo, e uma retomada de "carregar mais" preserva corretamente `seen_ids`/`category`/`query` (ou `url`/`type` pro X) na sessão reaberta.

O próprio `_x_open_session()`/`_xf_open_session()` vazava o driver que ele mesmo cria em qualquer falha que não fosse aquele único caminho de `TimeoutException` tratado explicitamente — um crash no meio da abertura (ex.: `invalid session id: session deleted as the browser has closed the connection`, visto ao vivo em produção) fazia com que a variável `driver` do chamador nunca fosse atribuída, então a limpeza usual do chamador (`if driver: driver.quit()`) virava um no-op, e o processo `chromedriver` órfão ficava pra trás (até o watchdog abaixo eventualmente pegá-lo, até 15 min depois). As duas funções agora envolvem o corpo inteiro num `try/except Exception: driver.quit(); raise`, então qualquer falha durante a abertura da sessão mata o driver na hora, antes da exceção chegar no chamador.

Essa máquina é o desktop pessoal do usuário, não um servidor dedicado — VSCode, uma janela do Chrome pessoal, MariaDB e o shell do desktop competem pela mesma RAM que as sessões headless do Chrome do scrapperx, e o swap foi visto completamente cheio. Sob esse tipo de pressão, um `tab crashed` pode acontecer tanto na primeira tentativa quanto na retentativa imediata, segundos depois — os logs reais de produção mostraram exatamente isso (X e xFree travando na tentativa 2/2 dentro do mesmo minuto). Duas mudanças resolvem isso: `_BROWSER_RETRY_ATTEMPTS` subiu de 2 pra 3, e toda retentativa (busca nova e retomada de "carregar mais") agora faz `time.sleep(2)` antes, dando uma chance de um pico momentâneo de memória/CPU passar antes de subir outra instância do Chrome.

Um backoff fixo de 2s ainda não bastava pra uma contenção mais longa: os logs de produção depois mostraram três buscas separadas (X, X de novo, xFree) esgotando as 3 tentativas dentro de uma janela de ~40s antes de se recuperar sozinhas, e uma aba do Chrome pessoal foi flagrada consumindo ~32% de CPU continuamente por 3,6h em segundo plano — contenção real e sustentada, não um pico isolado. O backoff agora é escalonado (3s → 6s → 9s entre tentativas) e `_BROWSER_RETRY_ATTEMPTS` subiu de 3 pra 4, dando até ~25-30s de janela total de retry pra sobreviver a uma contenção mais longa antes de desistir.

### Self-heal: reinício do worker depois que as tentativas se esgotam

Mesmo com 4 tentativas escalonadas, uma contenção sustentada ainda pode esgotar todas elas — nesse ponto, `_self_heal_restart()` faz mais uma coisa além de só mostrar o erro: manda `SIGTERM` pro próprio processo worker (`os.kill(os.getpid(), signal.SIGTERM)`). Esse é exatamente o mecanismo que a reciclagem de workers do `--max-requests` do próprio gunicorn usa internamente, então é um comportamento padrão e bem suportado, não um hack — o worker termina qualquer resposta em andamento, sai, e o arbiter do gunicorn (um processo separado, sempre vivo — confirmado via `ps`: arbiter e worker são pai/filho) sobe um novo na hora pra substituí-lo. O app roda sob uma unidade `systemd` (`Type=simple`, `Restart=always`) que rastreia o PID do *arbiter* via `exec gunicorn ...` no `start.sh`, não o do worker — então isso é totalmente transparente pro systemd, que nem percebe que um reinício em nível de worker aconteceu.

Pulado inteiramente se houver um download em andamento (`download_progress` tem alguma entrada com `status == "downloading"`) — `download_task()` roda como uma thread em background dentro desse mesmo processo worker e seria morta junto com ele. Antes de reiniciar, também roda `_ss_close()`, `_xf_close()` e `_watchdog_sweep()` pra uma limpeza best-effort de qualquer sessão rastreada ou chromedriver órfão.

**Ressalva importante**: isso não corrige a causa raiz de crashes por contenção (ex.: outro processo na máquina consumindo CPU) — reiniciar o worker do scrapperx não tem efeito nenhum numa aba do Chrome ou processo do VSCode não relacionados. Só garante que o estado interno do scrapperx fica limpo mais rápido do que o watchdog (até 120s depois) conseguiria, logo depois de um padrão de crash forte o bastante pra esgotar todas as tentativas. Validado simulando `os.kill` e alternando `download_progress`: confirmado que o reinício é pulado enquanto um download está ativo, e prossegue (chamando `os.kill` com `SIGTERM`) quando não há nenhum.

### Correção crítica: toda sessão do Chrome vazava seu diretório de perfil no disco

Investigando por que os crashes continuavam mesmo depois de tudo isso, o `/tmp` foi encontrado completamente cheio (7.3 GB, 100% de uso). Causa raiz: `_ss_driver()` cria um diretório único (`tempfile.mkdtemp()`) como `--user-data-dir` de cada sessão, mas **nenhum caminho de limpeza jamais o apagava** — nem `_ss_close()`, nem `_hard_kill_driver()`, nem o watchdog. O Chrome só limpa sozinho um diretório de perfil que ele mesmo cria; um fornecido via `--user-data-dir` nunca é tocado. Toda busca que esse app já rodou vazou um desses diretórios permanentemente — encontrados ~27 restantes (2 MB–870 MB cada) ao inspecionar o `/tmp` diretamente. Com o disco cheio, qualquer sessão *nova* do Chrome falha ao gravar seu perfil e trava na hora — muito provavelmente a causa real (ou pelo menos uma causa relevante) por trás do padrão de "tab crashed" perseguido nas seções acima, não só contenção externa de CPU.

Corrigido em todos os níveis: `_hard_kill_driver()` agora faz `shutil.rmtree()` no `--user-data-dir` marcado depois de matar a árvore de processos; a varredura de órfãos do watchdog extrai e remove o `--user-data-dir` do processo Chrome filho de cada chromedriver órfão encontrado antes de seguir adiante; todo `driver.quit()` avulso que restava nos caminhos de limpeza-em-falha do `/api/search` foi trocado por `_hard_kill_driver()`, pra também limpar o diretório em vez de só encerrar a sessão do WebDriver. Também removido `_selenium_search()`/`search_x_videos()` — um segundo caminho de busca do X, morto (não referenciado por nenhuma rota ativa), que montava seu próprio `--user-data-dir` inline e vazava completamente fora do alcance do `_hard_kill_driver`. Validado com três testes: `_hard_kill_driver` remove um diretório marcado, um crash simulado dentro de `_x_open_session` não deixa nada pra trás, e a varredura de órfãos do watchdog limpa um processo real gerado carregando um argumento `--user-data-dir`.

### Watchdog em background pros casos que a limpeza reativa não alcança

Retry e `_hard_kill_driver` só rodam quando um request handler de fato percebe que algo deu errado — nenhum dos dois ajuda se nenhuma requisição nova chegar pra sessão morta. Dois buracos reais:

- Um usuário inicia uma busca e depois só fecha a aba sem nunca mais chamar "carregar mais" — essa sessão do Chrome ficaria ociosa pra sempre; nada reconfere `_SS_TIMEOUT`/`_XF_SS_TIMEOUT` de forma reativa, a menos que uma requisição *nova* aconteça de referenciar aquele ID de sessão.
- O próprio processo do servidor é morto (`kill -9`, OOM) — o `_SS`/`_XF_SS` do processo seguinte começa vazio, sem ideia nenhuma de que a árvore antiga do chromedriver/Chrome ainda existe. É exatamente o vazamento de ~15h/~1.5GB que motivou o `_hard_kill_driver` em primeiro lugar, só que por um gatilho diferente (o próprio estado de rastreamento se perdeu, não um crash pro qual `_ss_close()` é chamado).

`_watchdog_sweep()` roda numa thread daemon (`_watchdog_loop`, a cada `_WATCHDOG_INTERVAL` = 120s, iniciada uma vez na importação do módulo) e faz duas coisas independentes: encerra `_SS`/`_XF_SS` se estiverem rastreadas mas ociosas além do timeout (mesmos `_ss_close()`/`_xf_close()` usados em todo o resto do código), e separadamente varre **todos** os processos `chromedriver` do sistema — matando (com seus filhos) qualquer um que não esteja sustentando uma sessão atualmente rastreada e que já esteja rodando há mais de `_WATCHDOG_ORPHAN_AGE` (900s, generosamente mais que qualquer navegação real leva, então nada legítimo fica "não-rastreado" por tanto tempo). Validado contra processos `chromedriver` reais de verdade: um rastreado sobreviveu a uma varredura com a checagem de idade forçada a disparar em tudo, um não-rastreado não sobreviveu — e na mesma execução também pegou e matou um `chromedriver` genuinamente órfão que tinha sobrado de um teste anterior, confirmando que a varredura funciona contra vazamentos reais, não só o caso sintético.

### Revalidação periódica dos cookies do X

Antes disso, `session_state["logged_in"]` só era (re)conferida no boot do servidor e quando o usuário clicava manualmente em "Validar" — se a sessão do X expirasse com o servidor rodando (o caso comum, já que restarts são raros), o app continuava achando que estava logado até uma busca ou upload de verdade bater num erro cru da API do X (foi isso que causou o incidente anterior do `"Failed to authenticate. API Error: 401 OAuth access token has expired."` chegando pro usuário em vez da tela de reautenticação).

`_cookie_revalidate_check()` roda de novo o mesmo `validate_cookies()` usado no boot/"Validar" e sincroniza `session_state["logged_in"]` com o resultado nos dois sentidos, chamada a cada `_COOKIE_REVALIDATE_INTERVAL` (1800s / 30 min — cookies não expiram rápido o bastante pra justificar bater na API da X com mais frequência) pela sua própria thread daemon (`_cookie_revalidate_loop`), independente do watchdog de processos acima, então uma checagem de cookie lenta nunca atrasa ele. Não faz nada se ainda não existe arquivo de cookies, e engole erros de rede sem mexer no estado existente (uma falha transiente ao *checar* não é evidência de que a sessão está de fato inválida). Validado com 4 casos: sem arquivo de cookies (não faz nada), sessão expirada (vira `True → False`), sessão válida de novo (vira `False → True`), e erro de rede durante a checagem (não trava, deixa o estado intocado).
