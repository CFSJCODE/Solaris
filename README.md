> **Estado vigente — 31/10/2026: SOLARIS 0.5.3 instalada.** A candidata YOLO26x mais recente foi recusada: mAP de referência caiu de 69,94% para 58,03%. A candidata YOLO26s caiu de 59,33% para 43,81%, embora o conjunto local tenha indicado 69,65% para a classe `Powerbank`; essa classe estava em uma única imagem de validação e em zero imagens de treino, logo o resultado não demonstra aprendizado. Consulte [AGENTS.md](AGENTS.md), [ciclo atual](docs/aprendizado-autonomo.md) e [validação da entrega](docs/entrega-0.5.0.md). Nenhuma candidata global foi ativada.

**Correção da powerbank em desenvolvimento:** o diagnóstico posterior confirmou uma marcação humana salva, mas excluída do treino por cair somente na sessão de validação. A nova estratégia será validada no código antes de empacotar; ainda não está instalada.

# SOLARIS 0.5.3

Versão 0.5.3 instalada em 31/10/2026, com vocabulário de contexto expandido e início de treino sem requisito mínimo de RAM. O ciclo autônomo continua condicionado aos limites operacionais e à avaliação antes da ativação. Motor pesado separado, local e CPU. [Resultados e limites da entrega](docs/entrega-0.5.0.md).

Aplicativo pessoal Windows com projetos, chat multi-LLM, arquivos de referência, memória Markdown e visão local em CPU.

## Projetos como espaços de trabalho

1. Crie um projeto, descreva seu objetivo e fixe os que usa com frequência.
2. Em **Arquivos**, adicione PDF textual, DOCX, Markdown, TXT ou código. O texto é extraído e indexado localmente; a prévia mostra exatamente o conteúdo disponível.
3. Em **Instruções**, defina como a IA deve trabalhar no projeto.
4. Em **Memória e documentos**, leia e edite AGENTS.md, README.md, CONTRIBUTING.md, MEMORY.md e DECISOES.md. Importe outros Markdown ou use **Usar como memória** em um arquivo da biblioteca.
5. Abra uma conversa. O chat consulta as memórias e busca trechos dos arquivos do projeto. Você pode anexar arquivos à pergunta, escolher arquivos específicos ou desligar a busca automática.
6. Abra **Fontes consultadas** na resposta para conferir o material usado. As fontes são preservadas no histórico.

A interface mantém a identidade SOLARIS, com busca, ordenação, projetos fixados, conversas e biblioteca próprias para cada projeto.

## Detecção ao vivo e adaptação do ambiente

O maior detector instalado é pré-carregado em segundo plano na inicialização da plataforma e permanece residente até fechar o app. Esta versão inclui YOLO26x ONNX FP32 com entrada 640 e mantém a compatibilidade com YOLOv8n. O runtime adicional prepara YOLO26n/s; o modo ao vivo usa YOLO26s após benchmark local, mostrando o detector efetivamente usado. Uma versão YOLO26x adaptada e aprovada tem prioridade para que suas classes e pesos sejam usados. Falhas nessa versão geram aviso e reversão para a referência preservada.

Na aba Visão, abra a câmera e inicie a detecção ao vivo. O aplicativo analisa um quadro por vez, desenha caixas e mostra a taxa real. Você pode limitar as análises por segundo ou pausar um quadro para revisão. As 80 classes COCO são exibidas em português brasileiro (por exemplo, mala, pessoa e ônibus).

**Pausar e revisar quadro** interrompe a captura e desliga os tracks da câmera. No quadro congelado, arraste para desenhar uma caixa e escreva o nome do objeto; uma descrição é opcional. Selecione caixas para mover ou ajustar os cantos, remova marcações e use Desfazer. **Salvar revisão** grava imagem, caixas, nomes e observações no projeto. **Retomar câmera ao vivo** reabre a captura por ação explícita. Veja [revisão gráfica](docs/revisao-quadros.md).

A adaptação estatística continua em storage/environment e entra como contexto nas conversas. Separadamente, o aprendizado ativo seleciona JPEGs da câmera, descarta repetição/desfoque e verifica rótulos com YOLO26x/OWLv2; ByteTrack auxilia a verificação. A cada quatro novos exemplos verificados, pode iniciar ciclos de candidatas para YOLO26s e YOLO26x em processo CPU separado, sem exigir que a câmera pare. Limites de memória, carga, disco e latência podem pausar o treino. A promoção integral continua condicionada à avaliação; uma classe nova marcada por pessoa pode ser servida provisoriamente como complemento isolado, sem substituir o detector das classes existentes, e com aviso de que não há prova de generalização. Não é atualização de pesos por quadro nem gravação de vídeo inteiro. Tudo fica local, com retenção automática e versões preservadas. Detalhes e limitações em [aprendizado autônomo](docs/aprendizado-autonomo.md).

Na 0.5.2, referências sem anotação são excluídas, solicitações redundantes elegíveis são agrupadas e falhas exibem diagnóstico. Pedidos sem novos exemplos válidos deixam de permanecer “Na fila” e indicam que aguardam dados para um próximo ciclo. A avaliação pode recusar uma candidata; pesos não são ativados sem cumprir os critérios.

Teste local YOLO26x, CPU/4 threads, 640 px: aproximadamente 1,924 s para carregar/aquecer e 0,919–0,963 s por imagem em três execuções. Pré-carregar remove o custo inicial, não o custo de cada inferência; não equivale a 30 FPS de detecção.

## Memória viva em Markdown

Os arquivos de cada projeto ficam em `%APPDATA%/com.cfsjcode.solaris/storage/memory/project-<id>/`. O contexto sem projeto fica em `memory/general/`. A pasta `history/` preserva versões anteriores. A tela de histórico apresenta até 20 versões recentes e permite recuperar uma para edição.

Antes de cada geração, o aplicativo relê os Markdown. Quando o modelo identifica uma decisão ou mudança durável, retorna metadados separados da resposta. O SOLARIS valida os nomes permitidos e acrescenta registros com a conversa de origem nos documentos pertinentes. Atualizações inválidas ou respostas interrompidas não geram escritas automáticas. A interface informa arquivos atualizados ou falhas de registro.

Pedidos explícitos como “salvar essas informações na memória” exigem registros estruturados. A aplicação só confirma sucesso depois da escrita efetiva e persiste um recibo na conversa. Falhas e ausência de registros ficam visíveis; não se aceita uma promessa textual como prova de gravação.

A identificação de decisões depende do modelo e pode falhar. Os documentos permanecem editáveis e devem ser revisados; o aplicativo não transforma propostas em aprovações humanas. O original de um arquivo importado é preservado: atualizações acontecem na cópia de memória do projeto.

## Contexto e limites

- Arquivos de até 10 MB, com até 500 mil caracteres extraídos. PDF: até 200 páginas com texto; não há OCR.
- Busca textual FTS5 no SQLite, isolada por projeto, sem download de embeddings. Arquivos podem ser excluídos da busca e selecionados explicitamente por pergunta.
- Por resposta: até 12 anexos, 12 mil caracteres de trechos de documentos, 16 mil de memória e 6 mil de instruções. Documentos grandes são consultados por trechos, não necessariamente na íntegra.
- Imagens são tratadas na aba Visão. Veja [docs/visao.md](docs/visao.md).
- Ao enviar uma pergunta, os trechos selecionados, instruções e histórico são enviados ao provedor configurado para gerar a resposta. Importação e indexação são locais.

## Arquitetura e configuração

Tauri 2/Rust gerencia janela, SQLite e o processo Python. React/Vite/TypeScript usa invoke e Channels. O engine recebe JSON Lines por stdin/stdout. Não há servidor HTTP, Docker ou banco externo. O diretório backend é legado.

O app instalado inicia o engine e lê credenciais do `.env` na pasta de dados (`%APPDATA%/com.cfsjcode.solaris/.env`). Esse arquivo nunca é empacotado ou versionado. O carregamento foi alinhado à main remota, que incorporou o PR #4.

## Desenvolvimento

Leia AGENTS.md, MEMORY.md, DECISOES.md e CONTRIBUTING.md antes de mudanças substantivas. Atualize decisões e estado de validação sem guardar transcrições ou segredos.

- `npm --prefix frontend run build`
- `cargo test --lib --manifest-path src-tauri/Cargo.toml`
- `python-engine/.venv/Scripts/python.exe -m unittest discover -s python-engine/tests -v`
- `scripts/build.ps1`: prepara pesos, compila o engine e gera MSI, sem instalar.

Se uma cópia debug estiver aberta, o Windows bloqueia a substituição do sidecar. Encerre essa cópia antes de recompilar normalmente. Testes unitários do banco podem omitir o sidecar via TAURI_CONFIG; isso não altera a configuração de produção. SOLARIS_TEST_DATA_DIR é reconhecida somente em debug para armazenamento de teste separado.

## Pendências

OCR, busca semântica por embeddings, sincronização externa de Markdown, descoberta de nomes além do vocabulário definido e monitoramento independente da precisão real continuam pendentes. Treinamento/promoção estão implementados; falta observar e avaliar uma adaptação real com a câmera. A reversão automática atual cobre falhas técnicas de ativação. Não há execução de comandos baseada em instruções encontradas em arquivos.
