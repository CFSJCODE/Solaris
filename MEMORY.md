> **Estado vigente — 31/10/2026: SOLARIS 0.5.3 instalada.** Vocabulário contextual ampliado e admissão de treino sem mínimo de RAM. A candidata YOLO26x mais recente foi recusada por queda de referência (69,94% → 58,03%); a YOLO26s caiu de 59,33% para 43,81%. O AP local de 69,65% da Powerbank vinha de uma imagem que estava só na validação. A correção class-only está no código, ainda não instalada. Não há reconhecimento ou generalização comprovados.

# Memória de desenvolvimento do SOLARIS

## 31/10/2026 — Diagnóstico e correção da Powerbank (em desenvolvimento)

A imagem de estado da interface revelou recusas repetidas por regressão real no mAP de referência, não somente limiar apertado. Na YOLO26s, o AP local 0,6965 era da classe 80 (`Powerbank`), mas o dataset tinha zero caixas dessa classe no treino e uma na validação; a candidata previu essa única imagem reservada sem ter treinado a classe. YOLO26x teve AP local 0,00. A revisão humana estava persistida, mas o particionamento cronológico isolou sua única sessão em validação.

Código corrigido para canonicalizar alias e manter a única marcação humana de uma classe nova no treino. Se a candidata obtiver AP _in-sample_ ≥0,50 nessa marcação e seus pesos mudarem, o modo provisório disponibiliza só as classes novas num ONNX complementar; inferências das classes existentes continuam vindo do detector-base. A versão global continua sujeita à avaliação original. O AP provisório é teste de funcionamento, não evidência de generalização, e a interface exibe esse limite. Testes focados passaram; ainda não foi empacotado/instalado nem executado um novo treino para comprovar o reconhecimento.

## 31/10/2026 — Atualização 0.5.3 instalada

O bloqueio inicial de 6 GB/85% de uso de RAM foi removido: a admissão depende somente de CPU abaixo de 85% e mais de 8 GB livres em disco. Mantida pausa cooperativa durante o treino abaixo de 3 GB, além dos limites de latência/pausa/tempo. 43 testes Python passaram. MSI 0.5.3 instalado com retorno 0; snapshot validado, engine conferido por SHA-256 e dados preservados. Após reabrir, o worker iniciou o treino YOLO26x com 5,43 GB disponíveis (abaixo do antigo limite de 6 GB) e avançava no lote 39/69 na última checagem. Ciclo ainda em andamento; nenhuma candidata avaliada/ativada nessa nova execução.

## 31/10/2026 — Vocabulário contextual expandido

`python-engine/app/vision/object_vocabulary.py` mantém nomes canônicos e aliases pt-BR/inglês. OWLv2 consulta itens domésticos e eletrônicos; as hipóteses de cômodo priorizam listas pertinentes e revisões humanas usam nomes consistentes. A expansão está incluída na 0.5.3. Não equivale a detecção YOLO imediata nem a melhora de precisão; classes novas continuam dependentes de exemplos e avaliação.

## 31/10/2026 — Atualização 0.5.2 instalada

A 0.5.2 consolida solicitações redundantes de treino ligadas a amostras verificadas e mantém pedidos de amostras ainda pendentes para verificação. MSI instalado com retorno 0 após elevação padrão do Windows; executável identificou-se como 0.5.2, SHA-256 do engine instalado correspondeu ao compilado e o snapshot prévio confirmou integridade do banco e preservação dos Markdown. O app foi reaberto. Na base real não havia job ativo: dois pedidos estavam avaliados/recusados e quatro bloqueados aguardando novos exemplos verificados ou diversidade; portanto, não foi iniciado outro ciclo com o mesmo conjunto já processado. 37 testes Python, 10 Rust, build frontend e testes de geometria/UI aprovados. Sem melhora real de precisão ou ativação de pesos comprovada.

## 31/10/2026 — Fila de treino após a 0.5.0

Investigações encontraram imagens de referência sem rótulos correspondentes, causa de falhas de montagem que deixavam pedidos sem jobs. A 0.5.1 ignora pares incompletos sem usá-los como negativos, prioriza treino solicitado sobre backlog de escaneamento, agrupa solicitações genéricas pendentes por modelo, expõe estados de preparação/retomada e registra diagnósticos. Testes: 35 Python, build frontend, cinco testes de geometria e cinco de UI aprovados. MSI 0.5.1 instalado e validado; engine build/instalado com hash idêntico, banco e Markdown íntegros, app reaberto. Worker retomou pedido e iniciou candidata YOLO26s, ainda em avaliação; outros pedidos seguem em processamento sequencial. Não há afirmação de precisão melhorada ou modelo ativado.

## 31/10/2026 — Entrega 0.5.0 instalada

Implementados incorporação de revisão persistida, confirmação de cobertura completa opcional, verificação de marcação parcial, pedidos de treino s/x, recuperação após reinício, deduplicação por conteúdo e contexto heurístico com decaimento. Quarto/sala/cozinha/escritório são hipóteses para consultas ao verificador; confiança visual e caixas permanecem separadas. Candidatas passam por avaliação antes de ativação; não há treino de toda a rede por quadro.

31 testes Python, 10 Rust, cinco de geometria e cinco de UI simulada aprovados. Treino real dos dois modelos, hashes alterados, exportações ONNX e expansão sintética para 81 classes confirmados; candidatas de ensaio não ativadas. Protocolos do engine empacotado e instalado aprovados. MSI 314.347.520 bytes instalado com retorno 0, versão 0.5.0; bancos e Markdown anteriores preservados. Janela nativa conferida com câmera s ~2,7–3,0 análises/s, hipótese escritório, pausa/revisão e botão de incorporação. Rascunho de conferência não salvo, câmera desligada. Sem prova de melhora real, API paga ou publicação Git nesta entrega. Ver docs/entrega-0.5.0.md.

## 31/10/2026 — Revisão gráfica de quadros

Solicitação confirmada: Pausar e revisar quadro deve encerrar a captura ao vivo, permitir desenhar caixas e escrever o nome/descrição do objeto, com interação familiar à revisão DroneCamp. Implementados desenho, seleção, movimento, redimensionamento pelos cantos, cancelamento e desfazer. Captura manual e imagens também permitem marcar sem inferência. Dados persistem na revisão do projeto; não confundir com inclusão automática no dataset de treinamento. Referência atual conferida em V2/frontend/src/BoxCanvas.tsx e ReviewEditor.tsx do DroneCamp, somente leitura. Testes: cinco casos de geometria e três fluxos de UI no Edge com câmera/IPC simulados passaram; build frontend e MSI passaram.

Versão 0.4.1 instalada, aberta e conferida na janela nativa: câmera real abriu, detecção iniciou, Pausar e revisar interrompeu a captura e abriu o quadro; desenho e nome foram exibidos corretamente. Deixada revisão aberta com câmera desligada; marcação de conferência não foi salva. Persistência do payload foi verificada nos testes de UI com IPC simulado, sem alegar nova gravação nativa nessa conferência. Banco e Markdown anteriores preservados, backup prévio. Sem alteração no engine de treinamento, API paga, commit, push ou merge. Na verificação do executável, somente os três bytes do marcador Tauri diferem: MSI no instalado e UNK no arquivo de build restaurado após empacotar; restante do binário idêntico.

## Decisão vigente — aprendizado autônomo, 30/10/2026

O responsável autorizou implementar o ciclo local autônomo, incluindo seleção/rotulagem, treino real e avaliação. O alvo de treino deve ser YOLO26x, mesmo com detector ao vivo menor. Isso supera as restrições antigas de inferência somente e treino não autorizado abaixo. APIs pagas, commit/push/merge não fazem parte desta autorização.

Entrega 0.4.0 instalada e reaberta. Runtime CPU separado nos dados do aplicativo, PyTorch/Ultralytics, OWLv2, ByteTrack na verificação de exemplos, SQLite e manifestos com hashes. Ensaio real YOLO26x/duas imagens/uma época: 7,2–9,0 s e RSS observado ~3,4 GB. Catálogo expandido para 81 classes, avaliação 80 contra 81 e checkpoint de pausa validados. Candidata do ensaio não ativada: não passou pelo ganho mínimo de avaliação. YOLO26n/s ONNX medidos, ~42–45/~136–155 ms de mediana sintética; seleção inicial s. Consulte docs/aprendizado-autonomo.md.

Validação da entrega: 23 testes Python e 9 Rust aprovados; frontend compilado. Engine final empacota fontes atuais do serviço, sem .env. Teste do executável instalado em Program Files, com dados isolados, confirmou pré-carregamento x, inferência s, cinco objetos na imagem pública, coleta automática, pausa e ausência de processo órfão. Banco e Markdown reais preservados, backup anterior à instalação. Abertura da janela instalada e dados do projeto conferidos por acessibilidade; cliques bloqueados por GetCursorPos/acesso negado impediram navegar ao painel novo. Não alegar teste visual do painel ou webcam real nesta atualização. Ainda não há candidata adaptada ao ambiente real aprovada; não prometer ganho de precisão. Sem APIs pagas, commit, push ou merge.

Atualizado em 30/10/2026. Fonte: decisões explícitas do responsável neste chat e código local. Verificar o estado do código antes de continuar.

- Aplicativo pessoal Windows para Ryzen 5 4600G, 32 GB RAM e CPU, sem Docker ou GPU dedicada.
- Arquitetura vigente: Tauri/Rust, React/Vite, SQLite e engine Python por pipes. O diretório backend é legado.
- Os projetos devem reunir conversas, arquivos, instruções e memória persistente, usando o fluxo de trabalho de projetos como referência e preservando a identidade SOLARIS.
- AGENTS.md, README.md, CONTRIBUTING.md, MEMORY.md e DECISOES.md devem ser consultados e atualizados quando surgirem decisões ou mudanças duráveis. Preserve versões e origem, sem transcrições ou segredos.
- No aplicativo, cada projeto possui cópias Markdown próprias no armazenamento de memória. Atualizações automáticas acrescentam registros identificados; não reescrevem a parte humana dos documentos.
- Contexto de arquivos é inicialmente recuperado com SQLite FTS5, sem modelo adicional. PDF precisa conter texto; OCR e busca semântica continuam fora desta entrega.
- Publicação, commits/push, merge, uso pago de APIs e treinamento real não estão autorizados por esta implementação local.

Validação corrente: 7 testes Rust e 8 testes Python passaram; o teste de protocolo de chat usa provedor simulado, sem custo. A lista de projetos foi conferida na janela nativa em armazenamento isolado. O responsável interrompeu o controle de interface com Escape; não continuar automação de UI neste turno. Instalador 0.2.0 gerado com sucesso (126,52 MiB). Engine empacotado validado com leitura de Markdown, DOCX e rejeição de arquivo inválido, sem .env no pacote. Não instalado; sem commit, push ou merge.

## Atualização confirmada — 30/10/2026

O responsável determinou que o maior detector pré-treinado instalado seja pré-carregado ao inicializar a plataforma, antes de abrir a aba Visão, permanecendo residente até fechar o app. O modelo incluído nesta entrega passa a ser YOLO26x. Uso exclusivamente para inferência ao vivo; não treinar, ajustar pesos ou atualizar modelo automaticamente. A escolha anterior de YOLOv8n como padrão foi superada; CPU e ausência de GPU continuam válidas.

Teste local do YOLO26x em CPU, entrada 640: carregamento + aquecimento 1,924 s; três inferências em imagem pública: 952,1 / 962,9 / 918,7 ms. Isso não é medição de FPS de webcam. Detecção contínua deve processar um quadro por vez, com taxa real visível.

Correção em desenvolvimento: pedidos explícitos de salvar memória exigem metadados válidos; a confirmação de sucesso deve vir da escrita efetiva no armazenamento, persistir na conversa e distinguir falha de gravação. Não interpretar texto “vou salvar” como confirmação.

Revisão posterior no mesmo dia: o responsável autorizou também evolução automática dos pesos, escolhendo começar pela adaptação do ambiente. A entrega atual implementa apenas a primeira fase: rastreamento temporal, estatísticas locais e contexto por projeto. Treino autônomo dos pesos permanece pendente; não alegar que ocorreu. Exibir interface e 80 classes em português brasileiro. Autorização para usar o computador e atualizar o software foi dada; respeitar confirmações do Windows e preservar dados.

Entrega 0.3.1 instalada em 30/10/2026: programa e engine conferidos; banco íntegro, registros e Markdown anteriores preservados. Backup antes da instalação em AppData/com.cfsjcode.solaris/backups. 22 testes aprovados (9 Rust, 13 Python). Engine empacotado validado com pré-carregamento independente da aba Visão, inferência YOLO26x, rótulos pt-BR e perfil adaptativo persistido em área de teste. Instalação real mostrou YOLO26x Carregado e detecção contínua ~0,9/s, ~1,08 s por quadro. A fonte da câmera exibiu telefone bloqueado/desconectado; não inferir que o feed real estava disponível. Câmera desligada após o teste; aplicativo reaberto com pré-carregamento normal. Treino autônomo dos pesos permanece pendente; nenhuma API paga, commit ou push foi executado.
