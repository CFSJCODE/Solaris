> **Estado vigente — 01/11/2026: SOLARIS 0.5.8 instalada** (Liquid Glass + Fluent UI 2, paleta preservada; validação visual nativa pendente). Desde a 0.5.3: vocabulário contextual ampliado e admissão de treino sem mínimo de RAM. Consulte [AGENTS.md](AGENTS.md), [ciclo atual](docs/aprendizado-autonomo.md) e [validação da entrega](docs/entrega-0.5.0.md). Registros de versões anteriores abaixo são históricos. Não há melhora real de precisão comprovada no ambiente do usuário.

# Decisões do SOLARIS

## 31/10/2026 — Nova classe humana como complemento isolado

Não aprovar um detector completo quando a referência das classes existentes regredir: as avaliações da powerbank registraram quedas de 15,52 pontos no YOLO26s e 11,91 pontos no YOLO26x. Corrigir a divisão para que uma marcação nova que só apareça na sessão mais recente participe do treino. Para uma classe explicitamente marcada, permitir somente um complemento provisório quando os pesos mudarem e a caixa humana obtiver AP _in-sample_ ≥0,50. O complemento fornece apenas os IDs novos e mantém o detector anterior para as classes antigas; avisar que o teste não demonstra generalização. Promoção integral mantém os limites de avaliação e exige evidência independente em sessões diversas.

## 31/10/2026 — Recuperação da fila de aprendizado

Pedidos genéricos pendentes usam os exemplos verificados atuais e são agrupados por modelo. Solicitações redundantes elegíveis ligadas a amostras também são consolidadas; amostras que ainda precisam de verificação permanecem associadas a um pedido. Treinos solicitados têm prioridade sobre a verificação de quadros sem relação com a revisão pedida. Imagens da referência sem arquivo de anotação correspondente são omitidas, nunca tratadas como fundo/negativos. Estados de preparação, treino, pausa, conclusão e falha são expostos; preparação interrompida volta à fila após reiniciar. A correção está instalada na 0.5.2. Nenhum critério de avaliação/promoção foi flexibilizado.

## 31/10/2026 — Resultado da fila após a 0.5.2

Após avaliar as candidatas s/x sem ativá-las, não havia job ativo nem solicitação em estado `queued`. Quatro pedidos foram bloqueados porque o conjunto já havia sido processado ou faltavam novos exemplos verificados/diversidade; dois pedidos constavam como avaliados. Não iniciar outro ciclo idêntico evita repetir treino sem dados novos. Os estados bloqueados devem informar a condição e não ser apresentados como “Na fila”.

## 31/10/2026 — Vocabulário contextual para objetos específicos

Usar uma taxonomia local curada com aliases para normalização e OWLv2 open-vocabulary para investigar exemplos, em vez de tratar COCO como um catálogo completo ou baixar um dataset amplo sem necessidade. Incluir objetos domésticos/eletrônicos e priorizar consultas conforme a hipótese de cômodo. O contexto só orienta a investigação; não cria caixas nem confirma objetos. Implementado na 0.5.3; nova classe exige evidências diversas e avaliação antes de ativação.

## 31/10/2026 — Admissão de treino com qualquer RAM disponível (0.5.3)

Não bloquear o início do worker pela quantidade ou percentual de RAM livre. Manter CPU abaixo de 85% e disco livre acima de 8 GB como limites de admissão; durante treinamento, preservar pausa cooperativa abaixo de 3 GB de RAM disponível para reduzir risco de esgotamento. Implementado na 0.5.3 e confirmado com treino YOLO26x iniciado abaixo do antigo limite de 6 GB.

## 31/10/2026 — Entrega 0.5.0 instalada

Implementados incorporação de revisão persistida, confirmação de cobertura completa opcional, verificação de marcação parcial, pedidos de treino s/x, recuperação após reinício, deduplicação por conteúdo e contexto heurístico com decaimento. Quarto/sala/cozinha/escritório são hipóteses para consultas ao verificador; confiança visual e caixas permanecem separadas. Candidatas passam por avaliação antes de ativação; não há treino de toda a rede por quadro.

31 testes Python, 10 Rust, cinco de geometria e cinco de UI simulada aprovados. Treino real dos dois modelos, hashes alterados, exportações ONNX e expansão sintética para 81 classes confirmados; candidatas de ensaio não ativadas. Protocolos do engine empacotado e instalado aprovados. MSI 314.347.520 bytes instalado com retorno 0, versão 0.5.0; bancos e Markdown anteriores preservados. Janela nativa conferida com câmera s ~2,7–3,0 análises/s, hipótese escritório, pausa/revisão e botão de incorporação. Rascunho de conferência não salvo, câmera desligada. Sem prova de melhora real, API paga ou publicação Git nesta entrega. Ver docs/entrega-0.5.0.md.

## 31/10/2026 — Marcação manual em quadro congelado

Pausar e revisar encerra a captura da câmera e fixa o último quadro analisado. Desenhar retângulos, escrever nome livre e observação opcional, selecionar/mover/redimensionar, remover/desfazer. Manter identidade SOLARIS e coordenadas da imagem original. Gravação explícita na revisão do projeto, schema 2, sem inventar IDs COCO nem confiança de modelo para marcas humanas. Retomada da câmera é explícita; retornos de detecção antigos não substituem o quadro. Revisão manual continua opcional e não altera os critérios do treinamento autônomo.

Entrega 0.4.1 instalada: cinco testes de coordenadas, três fluxos de UI simulados e build aprovados. No aplicativo instalado, conferidos câmera/detecção, congelamento, desenho e nome exibido. Nenhuma revisão de teste foi salva; câmera deixada desligada. Banco e documentos anteriores íntegros após atualização.

## 30/10/2026 — Projetos como espaços de trabalho

Confirmado pelo responsável: ampliar projetos com upload e leitura de arquivos, instruções próprias, conversas organizadas e fontes de contexto visíveis. Referências de interface não autorizam copiar a identidade visual de outro produto.

## 30/10/2026 — Markdown como memória viva

Confirmado pelo responsável: usar documentos como AGENTS.md, README.md e CONTRIBUTING.md como referência e contexto continuamente atualizados. Acrescentar MEMORY.md e DECISOES.md para contexto durável e registro de decisões. Manter origem, versões e edição humana.

Decisão de implementação: arquivos de memória pertencem ao projeto e são lidos novamente ao preparar cada resposta. Metadados estruturados de atualização ficam fora do texto visível do chat; só são aplicados a arquivos permitidos após uma resposta concluída. Conteúdo inválido ou interrompido não altera a memória.

## 30/10/2026 — Recuperação leve

Decisão de implementação: usar busca textual por trechos em SQLite, com isolamento por projeto e orçamento de contexto. Não instalar embeddings adicionais nesta etapa. Trechos e fontes são preservados junto à resposta.

## 30/10/2026 — Conflito do PR #5

A main remota incorporou o PR #4. O bloco de configuração do engine foi alinhado localmente à main; as funções novas foram preservadas. Nenhum merge ou push remoto realizado. O aviso no GitHub permanece até atualização autorizada da branch do PR.

## 30/10/2026 — Validação sem interferir no aplicativo em uso

A cópia debug foi aberta com armazenamento isolado e a lista de projetos foi conferida visualmente. O usuário interrompeu Computer Use com Escape. Nenhuma interação adicional de UI foi feita; a cópia permaneceu aberta. Testes do banco foram executados sem copiar o sidecar bloqueado, e o instalador 0.2 usa a saída release separada.

## 30/10/2026 — Entrega local 0.2.0

Instalador gerado em src-tauri/target/release/bundle/msi/Solaris_0.2.0_x64_en-US.msi. Foram aprovados 7 testes Rust e 8 Python, mais o teste de leitura de Markdown/DOCX no engine empacotado. Nenhuma API paga foi chamada. O app instalado não foi substituído; a cópia debug de validação permaneceu aberta após a interrupção do controle de interface pelo usuário. Mudanças locais sem commit/push/merge.

## 30/10/2026 — Pré-carregamento na inicialização e inferência somente

Confirmado explicitamente pelo responsável: pré-carregar o maior detector pré-treinado instalado na inicialização da plataforma. Mantê-lo na memória para detecção ao vivo, sem treinamento ou alteração dos pesos. YOLO26x incluído e validado em CPU. Seleção por escala x/l/m/s/n, com preferência pela família mais nova no desempate; falha de carregamento não deve causar troca silenciosa para um menor.

## 30/10/2026 — Confirmação de memória e gravação real

As imagens do aplicativo mostraram uma resposta prometendo salvar e Markdown ainda vazios. Correção: pedidos explícitos geram somente dados de memória; o aplicativo produz o recibo após persistir. Ausência de dados válidos gera falha explícita. O recibo e os arquivos alterados são persistidos com a resposta. Versão 0.3 em empacotamento, sem uso de API paga para validação.

## 30/10/2026 — Adaptação antes da evolução dos pesos

O responsável escolheu as duas frentes, começando pela adaptação ao ambiente, e autorizou uso local do computador e atualização do software. Implementação desta fase: associação de caixas, estabilização, estatísticas e recorrência por projeto, sem coleta contínua de imagens e sem treino de YOLO. A fase de pesos exige avaliação e reversão e continua pendente. Todas as classes devem ser exibidas em pt-BR. Foram aprovados 9 testes Rust e 13 Python antes do empacotamento 0.3.1.

## 30/10/2026 — Instalação e validação 0.3.1

Instalador de 299,69 MiB gerado e instalado com sucesso. Hash do engine instalado corresponde ao validado. Preservação do banco e dos arquivos Markdown conferida após a migração. Inicialização mostra YOLO26x carregado; fluxo ao vivo mediu ~0,9 análise/s. Feed da câmera mostrou um ícone de telefone bloqueado/desconectado; a validação de objetos e português foi feita também com imagem pública no engine empacotado. Após o teste, a câmera foi desligada e o app reaberto normalmente. A camada adaptativa aprende estatísticas de classes/caixas, não pesos de YOLO; treinamento dos pesos ainda é fase posterior.

O compilador Rust relatou falta de memória com o perfil anterior. A configuração Windows passou a gerar apenas rlib, com otimização 1 no crate da janela e um job de build. Inferência ONNX e pesos YOLO26x não foram reduzidos. O engine foi reconstruído em pasta de build separada após falha do empacotador.

## 30/10/2026 — Aprendizado autônomo com YOLO26x

Autorização explícita: implementar as tecnologias propostas sem seleção ou aprovação humana obrigatória durante o uso. Treinar sempre YOLO26x; permitir detector ao vivo menor. Usar processo CPU separado para dependências pesadas, preservar modelo original e versão anterior, avaliar antes de ativar. Coleta local limitada e transparente. OWLv2 investiga vocabulário adicional definido; não alegar descoberta semântica irrestrita. A avaliação local de rótulos automáticos é uma medida substituta. Reversão inicial cobre falhas de ativação, sem alegação de monitoramento independente da precisão real.

Entrega: versão 0.4.0 instalada e reaberta, dados anteriores preservados. Seleção inicial YOLO26s no vídeo; YOLO26x original residente. YOLO26x é o único alvo de treino, com parte da rede congelada inicialmente. Para mala/bolsa/mochila, exigir concordância também do OWLv2 antes de usar o rótulo. Retenção preserva ativa/anterior e checkpoints recuperáveis, limpando somente artefatos gerados. 32 testes unitários aprovados e testes reais de treino, expansão de catálogo, checkpoint, exportação e integração no engine instalado. Candidata do ensaio reprovada pelo critério de ganho, não ativada. Navegação visual final bloqueada pelo Windows; janela aberta e dados visíveis, sem validação da webcam real nesta atualização.

## 01/11/2026 — Liquid Glass + Fluent UI 2 na interface

Diretriz do responsável: modernizar materiais, profundidade, iluminação e movimento com princípios do Apple Liquid Glass e do Fluent UI 2, **sem alterar a paleta**. Implementado em camadas de tokens separadas (`frontend/src/styles/liquid/`), com `solaris.css` intacto e teste que falha se qualquer cor original mudar ou se surgir literal de cor novo. Refração real por lente SVG (SDF + `feDisplacementMap` em `backdrop-filter`) somente na topbar e no composer do chat; tiers `liquid`/`glass`/`solid` automáticos e ajustáveis pelo usuário. Conflitos de cor e tokens indefinidos (`--sol-accent`) registrados em `docs/design/liquid-glass-fluent.md` §7 para decisão humana, sem alteração automática.

Complemento (01/11/2026): `--sol-accent` passa a ser alias de `--sol-gold`, por decisão do responsável ("manter as cores originais"). O vidro foi reforçado após a avaliação de que parecia "apenas degradê": lente por Snell (n = 1,5), especular de contorno, tom multiplicativo no fundo com tinta menor, e navegação como lâmina flutuante refrativa.

Limitações resolvidas (01/11/2026, a pedido do responsável): cena WebGL2 com GLSL próprio desenha o fundo
e a lâmina de navegação com refração em toda a superfície, dispersão por canal, Fresnel e especular que
segue ponteiro ou giroscópio; lente SVG passou a cúpula inteira; barras fixas de vidro também em
Projetos; molas físicas em runtime para deformação ao pressionar. Shader sem cores próprias (tokens via
uniforms) e contraste testado no pior caso. WebGPU avaliado e não adotado. Detalhes no §11 do documento
de design.

## 01/11/2026 — Release 0.5.8 instalada

Versão 0.5.7 → 0.5.8 para entregar o Liquid Glass + Fluent UI 2 (PR #30) aprovado pelo responsável. MSI gerado por `scripts/build.ps1` e instalado com backup verificável antes; engine instalado idêntico ao compilado, bancos e Markdown preservados. A conferência visual na janela nativa e a medição de CPU/GPU na rolagem ficaram pendentes porque o acesso de controle à janela foi negado nesta sessão. Detalhes em `docs/entrega-0.5.0.md`, seção "Atualização 0.5.8 instalada".

## 01/11/2026 — Painel de métricas de uso

Pedido do responsável: métricas de uso equivalentes às do painel “Seu uso” do Claude. Implementado: cada resposta concluída grava um evento em `usage_events` (SQLite, sem chave estrangeira para preservar o histórico após exclusões) com provedor, modelo, tokens de entrada/saída e custo. Janelas: sessão deslizante (padrão 5 h, inicia na primeira mensagem após a anterior expirar), semana com reinício em dia/hora local configuráveis (padrão sábado 12:00) e limite por modelo como fração do limite semanal. Limites são orçamentos definidos pelo usuário, não cotas dos provedores; ainda não bloqueiam envios nem alteram o roteamento. Custo desconhecido é registrado como nulo (não zero) e o OpenRouter passa a informar o custo real quando disponível. Eventos anteriores a esta versão não existem; o uso começa a contar após a atualização.
