> **Atualização posterior neste mesmo dia:** o trabalho descrito como parcial abaixo foi implementado, validado e instalado na entrega 0.5.0. Consulte [registro atual](entrega-0.5.0.md) e [ciclo vigente](aprendizado-autonomo.md). Este arquivo preserva o ponto de retomada anterior; suas pendências não devem ser assumidas como estado atual sem conferir o registro de entrega.

# Continuidade da implementação — 31/10/2026

## Estado e escopo

Pedido vigente: manter memória/contexto Markdown atualizados para continuidade por outras IAs. Consolidar decisões e conceitos dos materiais anexados sem apresentar propostas como implementadas. Esta atualização documental não conclui o desenvolvimento do botão de treino nem atualiza o instalador.

Instalada: **0.4.1**. Em desenvolvimento local: incorporação de revisões, fila explícita de treino, treinamento separado de YOLO26s e YOLO26x, adaptação em ciclos durante o uso quando os recursos permitirem. Não houve instalação ou treino real dessa nova extensão. A versão no código continua 0.4.1; é necessário definir nova versão ao entregar.

## Alterações locais iniciadas — revisar antes de prosseguir

| Arquivo                                        | Trabalho iniciado                                                                                                                                          | Validação que falta                                                                                 |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| python-engine/app/vision/learning.py           | Tabelas human_reviews, training_requests, live_context; incorporação de revisão, pedidos s/x, latência média e sessões temporais                           | Migração em banco existente, quotas, duplicação/idempotência, concorrência e isolamento por projeto |
| python-engine/app/vision/learning_worker.py    | Mescla de marcação humana com verificação, prioridade de pedidos, datasets por modelo, treino s/x, progresso/loss, hashes de pesos e critérios de promoção | Testes integrados, pausas, cancelamento, ambos os modelos, regressões, datasets parciais e retenção |
| python-engine/app/vision/detector.py           | Preferência pela candidata s aprovada no vídeo; x para análise estática; identificação do modelo adaptado                                                  | Carregamento, troca, incompatibilidade e reversão no engine real                                    |
| python-engine/app/vision/learning_retention.py | Reconhecimento dos ponteiros ativos s                                                                                                                      | Proteção de ativo/anterior e limpeza de metadados órfãos                                            |
| python-engine/app/main.py                      | Mensagens learning_incorporate e learning_train_now                                                                                                        | Protocolo do executável real e erros propagados à UI                                                |
| src-tauri/src/db.rs                            | Recuperação de revisão persistida com escopo de projeto                                                                                                    | Integridade, acesso cruzado e exclusão                                                              |
| src-tauri/src/commands.rs e lib.rs             | Comandos de incorporação/treino e registro                                                                                                                 | Compilação e testes Rust após estas mudanças                                                        |
| frontend/src/pages/VisionPage.tsx              | Confirmação de quadro completo e botão de incorporar após salvar; recibos separados                                                                        | Testes de falha parcial, revisão humana, classes vazias e estado da câmera                          |
| frontend/src/components/LearningPanel.tsx      | Treinar contexto agora, fila s/x, progresso e métricas antes/depois                                                                                        | UI simulada e nativa com estados reais                                                              |

O frontend compilou e os módulos Python foram verificados quanto à sintaxe/compatibilidade durante o trabalho. Isso não substitui a bateria completa após as últimas alterações. Os testes anteriores a esta extensão não certificam o novo fluxo.

### Parâmetros experimentais no código parcial

Verificar no código antes de usar: coleta a cada 3 s, sessões de 120 s, dataset até 512 amostras, gatilho automático de 32 amostras verificadas em duas sessões; solicitação explícita pode gerar candidata com uma amostra. Alvos s e x, uma época, batch 1, imagem 320, uma thread, congelamento inicial de camadas e learning rate 0,0005. São parâmetros de engenharia experimentais, não prescrições matemáticas ou garantia de aprendizado.

O teste de promoção exige avaliação local separada e cobertura mínima; para classe nova há requisitos adicionais de diversidade e exemplos de validação. O sinal no código chamado independent_local_holdout/promotion_ready é uma condição operacional, **não prova estatística automática de independência**. A avaliação por rótulos automáticos continua substituta, mesmo quando o particionamento é separado.

A intenção do controle de recursos é permitir treino quando há RAM/disco e baixa pressão de CPU, incluindo contexto recente com latência aceitável; pedidos explícitos dispensam espera por ociosidade, não todos os limites. A segurança precisa ser medida com o x pré-carregado e vídeo ao vivo simultaneamente. Não prometer atualização de todos os pesos por quadro.

## Riscos concretos a resolver

1. Revisar separação temporal: selecionar sessão por UUID ordenado não garante ordem cronológica. Aplicar divisão cronológica e intervalo de exclusão entre treino/validação quando necessário.
2. Referência usada no treino/validação deixa de ser teste cego. Preservar conjunto final independente e registrar proveniência dos rótulos.
3. Tratar NaN/inf em loss, métricas e pesos explicitamente; candidata inválida nunca deve ser ativada.
4. Completar sinônimos pt-BR/canônicos: “televisão” não deve duplicar indevidamente “tv”; IDs originais permanecem estáveis. Classe realmente nova recebe novo ID controlado.
5. Confirmar marcações parciais: copiar somente caixas humanas confirmadas não torna o restante do quadro background. A verificação automática deve cobrir o que falta ou manter a amostra pendente.
6. Medir custo de hash dos tensores treináveis, processo professor e avaliação; limitar concorrência para manter o app responsivo.
7. Exercitar pausa/retomada, exclusão de projeto, retenção, falta de espaço, modelo corrompido e falha ao carregar ONNX. Proteger modelos ativos s/x e anteriores.
8. Evitar que o agendador treine repetidamente o mesmo conteúdo; fingerprint inclui rótulos e modelo, não só imagem. Confirmar deduplicação de pedidos.
9. A investigação OWLv2 usa vocabulário definido e exemplos nomeados; reconhecimento de qualquer classe desconhecida não está resolvido.
10. Semântica de ambiente (quarto/sala/cozinha) ainda não foi implementada como camada probabilística validada. Estatística de recorrência atual não é essa compreensão semântica.

## Ordem de retomada

1. Ler AGENTS e diferenças locais; preservar trabalho e dados existentes.
2. Criar testes significativos para incorporação parcial/completa, isolamento, filas s/x, catálogo, datasets sem vazamento, promoção recusada e retenção.
3. Compilar/testar Rust, Python nos ambientes adequados e frontend; atualizar testes de UI para os novos comandos.
4. Exercitar o protocolo real com armazenamento temporário. Executar ensaios pequenos de treino **dos dois modelos**, registrar pesos alterados e exportação; não ativar candidata que falhe nos critérios.
5. Medir câmera + treino concorrente na máquina real, pausas e pressão de memória. Distinguir treino técnico de melhora real de generalização.
6. Atualizar versão, gerar pacote, preservar backup, instalar e validar dados, inicialização e UI nativa. Somente então declarar a nova função entregue.
7. Aplicar incrementalmente o relatório acadêmico: qualidade de dados e validação primeiro; contexto probabilístico e detecção de mudança depois; comparação de alternativas com evidência.

## Git e histórico de conflito

PR #5: https://github.com/CFSJCODE/Solaris/pull/5. Conflito em python-engine/app/main.py resolvido com merge commit **47bbad19588a07702ad12d14890422be67c67363**, preservando o carregador do main e as funcionalidades da branch. Cinco casos isolados do carregador foram testados; nenhuma chave real foi exposta. Push efetuado para feat/memoria-projetos; estado consultado MERGEABLE/CLEAN. **PR não mergeado**. O trabalho local de visão não foi publicado por essa resolução.

Registro local: storage/pr5-resolution.json. Conferir o remoto novamente antes de novas operações. Não confundir a branch remota do PR com feat/continuar-projetos-visao, checkout local com alterações extensas.
