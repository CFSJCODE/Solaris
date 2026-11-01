# SOLARIS — Liquid Glass + Fluent UI 2

Diretriz aplicada em 01/11/2026. Objetivo: modernizar materiais, profundidade, iluminação e movimento
**sem alterar a paleta**. Todas as melhorias usam opacidade, blur, refração, sombras, geometria e
movimento sobre os tokens de cor já existentes.

## 1. Catálogo de cores preservadas

Fonte: `frontend/src/styles/solaris.css` (não modificado nesta mudança). O teste
`frontend/tests/design.test.mjs` falha se qualquer valor abaixo mudar ou se as camadas novas
redefinirem um token de cor ou introduzirem um literal de cor.

### Tokens de cor

| Token                | Tema   | HEX             | RGB                         | HSL                         |
| -------------------- | ------ | --------------- | --------------------------- | --------------------------- |
| `--sol-ember`        | escuro | `#EA6113`       | `rgb(234, 97, 19)`          | `hsl(22, 85%, 50%)`         |
| `--sol-flare`        | escuro | `#F88F22`       | `rgb(248, 143, 34)`         | `hsl(31, 94%, 55%)`         |
| `--sol-gold`         | escuro | `#FBB931`       | `rgb(251, 185, 49)`         | `hsl(40, 96%, 59%)`         |
| `--sol-glow`         | escuro | `#FFE3B3`       | `rgb(255, 227, 179)`        | `hsl(38, 100%, 85%)`        |
| `--sol-ink-950`      | escuro | `#0B0D12`       | `rgb(11, 13, 18)`           | `hsl(223, 24%, 6%)`         |
| `--sol-ink-900`      | escuro | `#11141B`       | `rgb(17, 20, 27)`           | `hsl(222, 23%, 9%)`         |
| `--sol-ink-850`      | escuro | `#171B25`       | `rgb(23, 27, 37)`           | `hsl(223, 23%, 12%)`        |
| `--sol-ink-800`      | escuro | `#202632`       | `rgb(32, 38, 50)`           | `hsl(220, 22%, 16%)`        |
| `--sol-bg`           | escuro | `#0B0D12`       | `rgb(11, 13, 18)`           | `hsl(223, 24%, 6%)`         |
| `--sol-surface`      | escuro | `#171B25`       | `rgb(23, 27, 37)`           | `hsl(223, 23%, 12%)`        |
| `--sol-text`         | escuro | `#F9F8F6`       | `rgb(249, 248, 246)`        | `hsl(40, 20%, 97%)`         |
| `--sol-text-muted`   | escuro | `#C1C4CB`       | `rgb(193, 196, 203)`        | `hsl(222, 9%, 78%)`         |
| `--sol-border`       | escuro | `#FFFFFF` α0.14 | `rgba(255, 255, 255, 0.14)` | `hsla(0, 0%, 100%, 0.14)`   |
| `--sol-reading`      | escuro | `#171B25` α0.96 | `rgba(23, 27, 37, 0.96)`    | `hsla(223, 23%, 12%, 0.96)` |
| `--sol-optical-tint` | escuro | `#181922` α0.2  | `rgba(24, 25, 34, 0.2)`     | `hsla(234, 17%, 11%, 0.2)`  |
| `--sol-success`      | escuro | `#37BE91`       | `rgb(55, 190, 145)`         | `hsl(160, 55%, 48%)`        |
| `--sol-warning`      | escuro | `#F5BD54`       | `rgb(245, 189, 84)`         | `hsl(39, 89%, 65%)`         |
| `--sol-error`        | escuro | `#FF7776`       | `rgb(255, 119, 118)`        | `hsl(0, 100%, 73%)`         |
| `--sol-info`         | escuro | `#7EAFFF`       | `rgb(126, 175, 255)`        | `hsl(217, 100%, 75%)`       |
| `--sol-bg`           | claro  | `#FFFCF8`       | `rgb(255, 252, 248)`        | `hsl(34, 100%, 99%)`        |
| `--sol-surface`      | claro  | `#F8F5F0`       | `rgb(248, 245, 240)`        | `hsl(38, 36%, 96%)`         |
| `--sol-text`         | claro  | `#20170F`       | `rgb(32, 23, 15)`           | `hsl(28, 36%, 9%)`          |
| `--sol-text-muted`   | claro  | `#625E59`       | `rgb(98, 94, 89)`           | `hsl(33, 5%, 37%)`          |
| `--sol-border`       | claro  | `#1E1914` α0.16 | `rgba(30, 25, 20, 0.16)`    | `hsla(30, 20%, 10%, 0.16)`  |
| `--sol-reading`      | claro  | `#FFFCF8` α0.98 | `rgba(255, 252, 248, 0.98)` | `hsla(34, 100%, 99%, 0.98)` |
| `--sol-optical-tint` | claro  | `#FFFCF7` α0.54 | `rgba(255, 252, 247, 0.54)` | `hsla(38, 100%, 98%, 0.54)` |

### Gradiente

| Token          | Valor                                                                         |
| -------------- | ----------------------------------------------------------------------------- |
| `--sol-sunset` | `linear-gradient(105deg, #EA6113 0%, #F88F22 33%, #FBB931 67%, #FFE3B3 100%)` |

### Valores derivados e literais já existentes no código (preservados)

| Onde                                                                       | Valor                                                   | Observação                                                       |
| -------------------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------- |
| `.sol-sunset-gradient`, `.sol-vision-canvas text`, `.sol-live-camera text` | `#0B0D12`                                               | igual a `ink-950`                                                |
| `.sol-badge-queue`                                                         | `#8888FF` (15 % fundo)                                  | literal pré-existente                                            |
| `.sol-badge-ok`, `.sol-metric-up`                                          | `#4CAF50`                                               | literal pré-existente                                            |
| `.sol-badge-warn`, `.sol-metric-down`, fallback de `--sol-warn`            | `#E07B39`                                               | literal pré-existente                                            |
| Conversa ativa (ChatPage)                                                  | `rgba(251, 185, 49, 0.10)`                              | `gold` a 10 %; movido para `.chat-conv-row.active` sem alteração |
| Markdown (ChatPage)                                                        | `--sol-md-*` = `gold`/`text` via `color-mix`, `ink-900` | inalterado                                                       |
| Diversos                                                                   | `color-mix(in srgb, <token> N%, transparent)`           | tons translúcidos de tokens existentes                           |

## 2. Arquitetura de tokens

| Camada           | Arquivo                                               | Conteúdo                                                                                                            |
| ---------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 1. Color         | `styles/solaris.css`                                  | paleta original, imutável                                                                                           |
| 2. Material      | `styles/liquid/tokens.css`                            | `--sol-glass-*` (mistura/tinta, blur, saturação), `--sol-specular-*`, `--sol-lens-*`, `--sol-mica-*`, `--sol-smoke` |
| 3. Elevation     | `styles/liquid/tokens.css`                            | `--sol-elev-0…5`, `--sol-depth-inset`, `--sol-z-*`                                                                  |
| 4. Geometry      | `styles/liquid/tokens.css`                            | `--sol-stroke-*`, `--sol-target-min`, raios concêntricos (`r_interno = r_externo − padding`)                        |
| 5. Motion        | `styles/liquid/tokens.css` + `design/spring.ts`       | `--sol-dur-feedback/state/panel`, `--sol-ease-spring-*` (springs amostradas em `linear()`)                          |
| 6. Accessibility | `styles/liquid/tokens.css` + `design/materialTier.ts` | `--sol-motion-scale`, `--sol-a11y-border`, `--sol-a11y-glass-floor`, tiers de material                              |

Toda tinta, brilho e sombra é `color-mix(in srgb, <token existente> N%, transparent)`: só a opacidade muda.

## 3. Hierarquia espacial (Fluent UI 2)

| Nível               | Material                                                                                 | Componentes                                                      |
| ------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| L0 Canvas           | **Mica**: `.sol-mica` (brilho radial monocromático de `ember` e `gold` sobre `--sol-bg`) | shell da aplicação                                               |
| L1 Content          | **Solid**: superfícies existentes + `--sol-elev-1` e brilho interno                      | cards de projeto, painéis, tabelas, formulários, mensagens       |
| L2 Functional Glass | **Liquid Glass Regular/Clear**                                                           | navegação lateral, topbar do chat, composer                      |
| L2 Structural       | tonal estável, sem blur                                                                  | lista de conversas                                               |
| L3 Overlay          | **Acrylic** + **Smoke**                                                                  | popover de arquivos (acrylic), diálogos (sólido elevado + smoke) |

Superfícies refrativas ativas por tela: no máximo 2 (topbar e composer), conforme a "regra de ouro" do
design system.

## 4. Liquid Glass — implementação

- **Refração/lensing** (`design/lensMap.ts`): SDF de retângulo arredondado; perfil de borda squircle
  `h(u) = (1 − (1 − u)^4)^(1/4)`; o deslocamento segue `−∇sdf` com intensidade proporcional à inclinação,
  forte na borda e nulo no centro (texto central nunca distorce). O mapa vira um PNG (meia resolução,
  memoizado) usado por `feImage` + `feDisplacementMap` em `backdrop-filter: blur() url(#lente) saturate()`.
- **Specular highlights**: borda luminosa com gradiente na direção da luz (`--sol-light-angle`), máscara
  `content-box`/`exclude`; brilho de topo (`sheen`) e espessura física (`--sol-depth-inset`).
- **Interactive lighting**: um único listener delegado, limitado por `requestAnimationFrame`, grava
  `--sol-light-x/y` só no elemento sob o ponteiro (`.sol-lit`, `.btn-primary`, `.sol-btn-accent`).
- **Adaptive material**: a topbar aumenta a tinta de 42 % para 86 % conforme o conteúdo rola por baixo,
  via `animation-timeline: scroll()` (sem JS); o contraste mínimo é garantido por teste.
- **Tiers progressivos** (`data-material` no `<html>`): `liquid` (lente + blur + luz, Chromium/WebView2),
  `glass` (blur + luz), `solid` (opaco). Escolha automática por capacidade e preferências do sistema, com
  controle manual "Superfícies" na navegação.

## 5. Movimento

Springs amortecidas (`ζ ≈ 0,86–0,90`, overshoot < 0,6 %) resolvidas analiticamente e amostradas em
`linear()`; fallback `cubic-bezier` quando `linear()` não é suportado.

| Spring   | Uso                                     | Duração |
| -------- | --------------------------------------- | ------- |
| `snappy` | pressionar/soltar, toggles              | 138 ms  |
| `smooth` | indicador de navegação, popovers, cards | 267 ms  |
| `gentle` | diálogos                                | 354 ms  |

- Indicador da navegação faz _morphing_ entre itens (translateY + altura) com cor de destaque original.
- Diálogos crescem a partir do controle que os abriu (`transform-origin` calculado) e devolvem o foco a ele.
- Somente `transform` e `opacity` são animados, exceto a largura da navegação ao recolher (ação do usuário).

## 6. Acessibilidade

- `prefers-reduced-motion`: durações → 1 ms e `--sol-motion-scale: 0` (sem deslocamentos).
- `prefers-reduced-transparency` e `forced-colors`: tier `solid`; `forced-colors` usa cores do sistema.
- `prefers-contrast: more`: tier `solid` no automático, bordas com `--sol-text-muted`, piso de opacidade 96 %.
- Composer e topbar: contraste AA verificado no pior caso (vidro sobre `#FFE3B3`, sem média de blur).
- Botão de apagar conversa agora aparece com foco de teclado; ícones da navegação são `aria-hidden` e a
  navegação recolhida usa `aria-label`; campo de mensagem e botão enviar têm nome acessível.
- Alvos: navegação 44 px; `--sol-target-min` 32 px (ponteiro fino) / 44 px (toque).

## 7. Conflitos registrados para revisão (cores não alteradas)

1. **"+ Nova conversa"** usava texto `#FFFFFF` sobre `--sol-sunset` (≈3,4:1 no `ember`, ≈1,2:1 no `glow`).
   Aplicada a regra já existente no design system §3 (texto `ink-950` sobre laranja): agora usa
   `--sol-ink-950`. Nenhum token mudou.
2. **Foco no tema claro**: contorno `gold` sobre `paper` tem ≈1,7:1 (WCAG 2.4.11 pede 3:1). O tema claro não
   está ativo no app; manter registrado.
3. **Tokens referenciados mas não definidos** em `solaris.css`: `--sol-accent`, `--sol-warn` (com fallback),
   `--sol-surface-raised` (com fallback), `--sol-duration-fast`, `--sol-font-display`, `--sol-optical-surface`
   (com fallback). Sem `--sol-accent`, `.sol-progress-fill`, `.sol-badge-active`, `.sol-feedback`,
   `.sol-project-hint` e `.sol-train-card` perdem a cor pretendida (a barra de progresso fica invisível).
   Não foi criado valor para não reinterpretar a paleta: decidir qual cor original (`gold`? `flare`?)
   deve ser o `accent`.
4. **Literais fora da paleta** já existentes nos badges (`#8888FF`, `#4CAF50`, `#E07B39`): preservados.
5. **Mica**: o Windows Mica real amostra o papel de parede; a janela Tauri é opaca (`transparent: false`),
   então o canvas usa brilho ambiente monocromático das cores originais, como previsto no design system
   (L0 "gradiente ambiental discreto"). Revisar se esse brilho é aceito como "não novo gradiente".

## 8. Performance

- Lente só em 2 superfícies; mapa gerado em meia resolução, memoizado por tamanho e regenerado apenas via
  `ResizeObserver` + rAF.
- Blur de 6–28 px somente em superfícies funcionais (nunca em tabelas, gráficos ou feeds).
- Nenhuma animação contínua decorativa; luz interativa só escreve estilo enquanto o ponteiro se move.
- Em Ryzen 5 4600G (Vega iGPU), o tier automático é `liquid`; com menos de 4 threads, pouca memória ou
  economia de dados cai para `glass`.

## 9. Testes

- `npm run test:design` — paleta imutável, ausência de literais novos, springs ↔ CSS, geometria da lente,
  resolução de tiers e contraste WCAG.
- `npm run build` — TypeScript + Vite.
