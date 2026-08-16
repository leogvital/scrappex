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
- Login do X (cookies) revalidado automaticamente no boot do servidor
- Publicação de tweet com vídeo (upload chunked com progresso real)
- Compatibilidade com Windows (Waitress no lugar do Gunicorn, scripts `.bat` equivalentes aos `.sh`)

### Downloads
- Download único e em lote, com seleção de formato/qualidade via yt-dlp
- Downloads em background sobrevivem a fechar o navegador (retomados via `localStorage` ao reabrir)
- Biblioteca local com player, exclusão e streaming

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

---

## 🐛 Limitações conhecidas (não são bugs para corrigir — são limites reais do site de origem)

- **Pornhub / Trans**: sem endpoint de busca por palavra-chave no site — a busca cai para o feed de destaque da categoria
- **XVideos / Home**: a página inicial de cada categoria não pagina (mesmo conteúdo em toda página) — sem "carregar mais"
- **xFree**: precisa de Selenium (não HTTP puro) porque o site carrega conteúdo via infinite-scroll client-side e bloqueia bots nas categorias Gay/Trans

---

## 🔧 Próximos passos propostos

### Robustez / manutenção
- [ ] Alerta/log estruturado quando um scraper parar de bater (sinal de que o site mudou o HTML e o parser quebrou)

### Novas plataformas
- [ ] Definir com o usuário quais sites entram em seguida (candidatos a levantar: outros agregadores com filtro de orientação, sites com API pública, etc.)

### UI/UX
- [ ] Busca simultânea em todas as plataformas de uma vez ("buscar em tudo")
- [ ] Fila de downloads com pausar/cancelar (hoje só cancela fechando a aba)
- [ ] Histórico/favoritos de busca
- [ ] Tema claro (hoje só existe o escuro)

### Segurança / operação
- [ ] Rate limit no `/api/auth/app-login` (proteção básica contra força bruta, mesmo sendo uso pessoal)

---

## Notas de operação

- Deploy sempre via usuário `touch` (`su - touch -c '...'` ou `su touch -c '...'`, nunca como root — veja o README)
- Sempre ler o README antes de mexer, atualizar depois de cada deploy
