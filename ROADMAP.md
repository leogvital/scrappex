# Roadmap — X Video Scraper

Status do projeto e próximos passos. Mantido junto com o [README.md](README.md) (que documenta *como* cada coisa funciona — este arquivo documenta *o que* já existe e *o que falta*).

---

## ✅ Feito

### Plataformas
| Site | Busca | Home | Categoria | Mecanismo |
|---|---|---|---|---|
| X (Twitter) | Palavra-chave, hashtag, usuário | Para Você, Seguindo | — | Selenium |
| XHamster | ✓ | ✓ | Hétero/Gay/Trans | HTTP |
| XVideos | ✓ | ✓ (sem paginação — limitação do site) | Hétero/Gay/Trans | HTTP |
| xFree | ✓ | ✓ | Hétero/Gay/Trans/Tudo | Selenium (bypass de Cloudflare) |
| Pornhub | ✓ (Trans sem busca por texto — limitação do site) | ✓ | Hétero/Gay/Sáfica/Trans | HTTP + `curl_cffi` (impersonation de TLS) |

### Conta e sessão
- Login do app com usuário/senha configuráveis via `.env.local` (fora do repositório — veja `.env.local.example`), sessão persistente — sobrevive a fechar o navegador (cookie de 30 dias) e a reiniciar o servidor (chave secreta salva em disco)
- Rate limit no `/api/auth/app-login` — 5 tentativas erradas por IP a cada 5 minutos, depois bloqueia (mesmo a senha certa) com uma mensagem de "aguarde Xs"; em memória só (sem Redis — `--workers 1` já não tem estado pra sincronizar entre processos), reseta num restart, mas isso é inofensivo aqui. Um login certo limpa o histórico de falhas daquele IP na hora
- Login do X (cookies) revalidado automaticamente no boot do servidor
- Publicação de tweet com vídeo (upload chunked com progresso real)
- Compatibilidade com Windows (Waitress no lugar do Gunicorn, scripts `.bat` equivalentes aos `.sh`)

### Downloads
- Download único e em lote, com seleção de formato/qualidade via yt-dlp
- Downloads em background sobrevivem a fechar o navegador (retomados via `localStorage` ao reabrir)
- Biblioteca local com player, exclusão e streaming

### UI/UX
- Histórico e favoritos de busca — cada busca bem-sucedida (qualquer plataforma) entra num histórico persistido em `localStorage`; buscas repetidas (mesma plataforma+tipo+query+categoria) se movem pro topo em vez de duplicar; favoritar uma entrada a protege de ser apagada por "Limpar histórico" e sobrevive a re-execuções; clicar numa entrada reconfigura a UI e refaz a busca
- Busca simultânea em todas as plataformas ("🌐 Tudo") — busca a mesma palavra-chave em 𝕏, xHamster, XVideos, xFree e Pornhub **sequencialmente** (não em paralelo — ver "sessão por site" abaixo), com os resultados de cada plataforma aparecendo assim que chegam e uma badge indicando a origem de cada card. Tem "carregar mais" independente por plataforma e seleção em lote pra baixar vários vídeos de plataformas diferentes de uma vez (fechando os dois cortes de escopo da v1)
- **Sessão por site** (`_SITE_SS` deixou de ser um dict único e virou um slot por site — xHamster/XVideos/Pornhub) — antes, como os três compartilhavam um único slot de sessão no backend, uma busca subsequente evictava a sessão da anterior; isso não importava enquanto só dava pra ver uma plataforma de cada vez, mas quebrava silenciosamente o "carregar mais" no modo "🌐 Tudo" pra pelo menos duas das três plataformas (a sessão delas já tinha sido substituída antes mesmo do usuário clicar em algo). Corrigido dando um slot independente pra cada site, localizado por `search_id` em vez de assumido como "o único ativo agora"
- Fila de downloads com pausar/cancelar/retomar — yt-dlp não tem "pausar" nativo, então pausar na prática é: sinalizar o hook de progresso pra abortar (levanta uma exceção, capturada pelo `download_task`) e deixar o arquivo `.part` no disco; retomar é simplesmente chamar `/api/download/start` de novo com a mesma URL/formato — como o nome de saída é determinístico, o yt-dlp encontra o `.part` existente e continua via HTTP Range requests, sem código extra de "resume". Cancelar usa o mesmo sinal, mas some com o `.part` (e `.ytdl`) em vez de preservá-lo; cancelar um download já pausado (sem thread rodando) apaga o arquivo direto na rota, sem precisar sinalizar nada. Controles de pausar/cancelar/retomar disponíveis em qualquer lugar que mostra progresso de download: modal de formato único, modal de download em lote e a bandeja de downloads em background
- Tema claro — só a paleta neutra (fundos/bordas/texto) é tematizada via variáveis CSS (`:root` = escuro padrão, `html[data-theme="light"]` = claro); cores de acento/semânticas (azul, vermelho, verde, amarelo) e as superfícies sempre-escuras do player em tela cheia (`PlayerModal`) ficam constantes nos dois temas, igual ao próprio tema claro do X/Twitter. Escolha persistida em `localStorage`, um script inline antes do React montar evita flash do tema errado no primeiro carregamento pra quem já escolheu claro
- **Busca roda em background no servidor** (mesmo padrão dos downloads) — antes, uma busca (principalmente X/xFree via Selenium, ou "buscar em tudo" rodando 5 plataformas seguidas) ficava presa num único `fetch()` bloqueado durante todo o tempo que levasse; se a aba fosse pra segundo plano (tela do celular apaga, troca de app), navegadores mobile suspendem/limitam JS e rede, podendo derrubar a requisição e perder a busca inteira. Agora `/api/search/start` e `/api/search/start_all` disparam o trabalho de verdade numa thread no servidor e devolvem um `task_id` na hora; o cliente só faz polling em `/api/search/task/<tid>` (a cada 1,5s), com o `task_id` salvo em `localStorage` — fechar e reabrir a aba (ou o sistema matar uma aba em segundo plano) reconecta na busca que continuou rodando o tempo todo, e o resultado aparece pronto. `/api/search` continua existindo e funcionando exatamente como antes (chamada síncrona) — os novos endpoints só reaproveitam a view existente via `test_request_context` do Flask, sem duplicar nenhuma lógica de scraping. Escopo consciente: só a busca nova ficou assíncrona; "carregar mais" (`/api/search/more`) continua síncrono, já que costuma ser rápido e é disparado com o usuário já engajado olhando os resultados, não "saindo e voltando depois"

### Correções de robustez já feitas
- Bloqueio de TLS fingerprint do Pornhub contra o yt-dlp (via `curl_cffi`)
- Endpoint de validação de cookies do X descontinuado pela própria X (`verify_credentials.json` → trocado por uma prova real de upload)
- Estado de login preso em `True` mesmo com sessão expirada (dessincronia corrigida)
- Thumbnails faltando na Home do Pornhub (atributo de card diferente)
- Duplicatas entre páginas na paginação do Pornhub (dedup por ID)
- Erro de permissão do *control socket* do Gunicorn 26 (`--no-control-socket`)
- Download travado ao clicar "Baixar" durante o carregamento automático de mais vídeos (worker `sync` do Gunicorn → `gthread` + 4 threads)
- Vazamento de ~1-1.5 GB de RAM por sessão do Chrome que trava sozinha (`_hard_kill_driver`)
- Retry automático quando o Selenium (X ou xFree) cai com erro transiente de I/O do Chrome (`Connection refused`, `tab crashed`) — reabre a sessão e retoma de onde parou, sem duplicar itens já mostrados
- Watchdog em background (`_watchdog_sweep`, a cada 120s) encerra sessões ociosas e mata processos chromedriver órfãos mais velhos que 15 min — cobre os casos que o cleanup reativo não pega (aba fechada sem nunca mais chamar "carregar mais", ou o próprio servidor sendo morto e perdendo o rastro da sessão)
- Revalidação periódica dos cookies do X (`_cookie_revalidate_check`, a cada 30 min) — antes a sessão só era reconferida no boot ou ao clicar "Validar"; se expirasse com o servidor rodando, o app continuava achando que estava logado até um erro cru da API aparecer numa busca/upload
- Vazamento de processo `chromedriver` órfão quando a sessão do X/xFree caía logo na abertura (ex.: `invalid session id` por o Chrome ter fechado a conexão) — `_x_open_session`/`_xf_open_session` não tinham um `try/except` cobrindo todo o corpo, então qualquer erro fora do caminho já tratado (timeout) deixava o driver sem `quit()`; agora qualquer exceção durante a abertura mata o driver antes de propagar
- Retries do X/xFree esgotando as duas tentativas de volta em segundos, sob pressão real de memória da máquina (é o desktop pessoal do usuário, não um servidor dedicado — VSCode, Chrome pessoal, mariadb e gnome-shell competem pela mesma RAM) — adicionado um `sleep(2)` antes de cada nova tentativa (busca nova e retomada de "carregar mais"), pra dar tempo de um pico momentâneo de memória/CPU passar, e o número de tentativas subiu de 2 para 3
- O backoff fixo de 2s ainda não bastava pra picos de contenção mais longos (~40s vistos em produção, com uma aba do Chrome pessoal consumindo ~32% de CPU continuamente por 3,6h) — trocado por backoff escalonado (3s/6s/9s) e o número de tentativas subiu de 3 para 4, dando até ~25-30s de janela total pra sobreviver a uma contenção mais longa antes de desistir
- Self-heal: se as 4 tentativas de retry se esgotarem com um erro transiente (`_self_heal_restart`), o worker do gunicorn se reinicia sozinho (`SIGTERM` no próprio processo — o arbiter do gunicorn sobe um substituto na hora, mesmo mecanismo do `--max-requests`), pulando se houver um download em andamento (roda como thread em background no mesmo worker). Não corrige a causa raiz (contenção externa de CPU/memória), só garante um estado limpo mais rápido do que o watchdog (até 120s depois) conseguiria
- **Vazamento crítico de disco**: `_ss_driver()` cria um diretório único (`tempfile.mkdtemp()`) em `/tmp` como `--user-data-dir` de cada sessão do Chrome, mas nenhum caminho de limpeza (`_ss_close`/`_xf_close`/`_hard_kill_driver`/watchdog) jamais apagava esse diretório do disco — Chrome não limpa sozinho um `--user-data-dir` fornecido externamente (só limpa perfis que ele mesmo cria). Achado ao investigar por que o `/tmp` do servidor chegou a 100% cheio (7.3 GB, ~27 diretórios de sessões antigas nunca removidos): com o disco cheio, qualquer sessão nova do Chrome falha ao gravar seu perfil e trava na hora — muito provavelmente a causa real (ou uma causa relevante) por trás de boa parte dos "tab crashed" que este roadmap vinha atribuindo só à contenção de CPU. Corrigido: `_hard_kill_driver` agora apaga o `--user-data-dir` da sessão depois de matar os processos; a varredura de órfãos do watchdog também extrai e apaga o `--user-data-dir` de cada chromedriver órfão encontrado; todo `driver.quit()` avulso nos pontos de limpeza-em-falha do `/api/search` foi trocado por `_hard_kill_driver()` pelo mesmo motivo. De quebra, removido `_selenium_search`/`search_x_videos` — um segundo caminho de busca do X, morto/não referenciado por nenhuma rota ativa, que também vazava seu próprio `--user-data-dir` de um jeito totalmente não seguido por `_hard_kill_driver`
- Alerta/log estruturado quando um scraper para de bater (`_record_scraper_outcome`) — uma exceção já aparece na hora como erro pro usuário; o buraco era o caso *silencioso*: a requisição "funciona" (200 OK, sem exceção) mas o parser não extrai nada, porque o site mudou o HTML/JSON por baixo de um seletor/chave frágil. Rastreia uma sequência de buscas *home/categoria* seguidas sem nenhum resultado por plataforma (não buscas por palavra-chave — uma busca rara pode legitimamente dar zero, mas o feed/categoria de uma plataforma deveria sempre ter conteúdo); qualquer sucesso zera a sequência. A partir de 5 seguidas sem resultado, loga um `[PARSER-ALERT]` bem marcado no log (grep fácil); se continuar quebrado, realerta a cada 10 falhas seguidas em vez de floodar o log a cada chamada

---

## 🐛 Limitações conhecidas (não são bugs para corrigir — são limites reais do site de origem)

- **Pornhub / Trans**: sem endpoint de busca por palavra-chave no site — a busca cai para o feed de destaque da categoria
- **XVideos / Home**: a página inicial de cada categoria não pagina (mesmo conteúdo em toda página) — sem "carregar mais"
- **xFree**: precisa de Selenium (não HTTP puro) porque o site carrega conteúdo via infinite-scroll client-side e bloqueia bots nas categorias Gay/Trans

---

## 🔧 Próximos passos propostos

### Novas plataformas
- [ ] Definir com o usuário quais sites entram em seguida (candidatos a levantar: outros agregadores com filtro de orientação, sites com API pública, etc.)

---

## Notas de operação

- Deploy sempre via usuário `touch` (`su - touch -c '...'` ou `su touch -c '...'`, nunca como root — veja o README)
- Sempre ler o README antes de mexer, atualizar depois de cada deploy
