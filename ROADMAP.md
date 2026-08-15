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

---

## 🐛 Limitações conhecidas (não são bugs para corrigir — são limites reais do site de origem)

- **Pornhub / Trans**: sem endpoint de busca por palavra-chave no site — a busca cai para o feed de destaque da categoria
- **XVideos / Home**: a página inicial de cada categoria não pagina (mesmo conteúdo em toda página) — sem "carregar mais"
- **xFree**: precisa de Selenium (não HTTP puro) porque o site carrega conteúdo via infinite-scroll client-side e bloqueia bots nas categorias Gay/Trans

---

## 🔧 Próximos passos propostos

### Robustez / manutenção
- [ ] Retry automático quando o Selenium (X ou xFree) cair com erro transiente de I/O do Chrome
- [ ] Revalidação periódica dos cookies do X (não só no boot) — hoje a sessão só é reconferida no restart ou ao clicar "Validar"
- [ ] Watchdog para matar processos Chrome/chromedriver órfãos, caso uma sessão trave no meio
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
