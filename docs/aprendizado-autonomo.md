# Aprendizado autônomo local — 0.5.3

Estado em 31/10/2026: extensão s/x, correções da fila, vocabulário contextual e admissão de treino sem requisito mínimo de RAM instalados na 0.5.3; validação na seção “Atualização 0.5.3 instalada” do [registro da entrega](entrega-0.5.0.md). O [histórico 0.4](historico-aprendizado-0.4.md) preserva parâmetros e evidências anteriores, que não descrevem o ciclo atual.

### Expansão do vocabulário contextual — 0.5.3

`object_vocabulary.py` mantém um catálogo local curado de nomes canônicos e aliases pt-BR/inglês. A lista inclui caixa de som, power bank/bateria externa, armários (genérico, cozinha e ferramentas), janela, porta, multímetro e itens relacionados de eletrônica/oficina. As consultas OWLv2 são priorizadas pelo cômodo estimado; rótulos humanos equivalentes convergem para a mesma classe. OWLv2 serve para investigar exemplos; isso não faz as classes aparecerem imediatamente na detecção ao vivo. Qualquer classe nova continua sujeita aos requisitos de evidência e avaliação.

### Admissão sem mínimo de RAM — 0.5.3

A quantidade e o percentual de RAM deixaram de bloquear o início. CPU abaixo de 85% e disco livre acima de 8 GB permanecem como critérios; se a memória disponível cair abaixo de 3 GB durante o treino, ele pausa cooperativamente. 43 testes Python passaram. Após instalar e reabrir a aplicação, o worker iniciou YOLO26x abaixo do antigo mínimo de 6 GB; na última checagem avançava no lote 39/69. A avaliação desse ciclo ainda está pendente.

### Consolidação de solicitações ligadas a amostras — 31/10/2026

A 0.5.2 agrupa solicitações elegíveis de amostras verificadas por modelo e preserva pedidos associados a amostras que ainda precisam de verificação. Na fila instalada, duas candidatas foram avaliadas e recusadas, sem ativação. Os pedidos restantes passaram a `blocked` com a mensagem de que o conjunto já foi processado ou ainda faltam exemplos verificados/diversidade; não havia job ativo nem pedido `queued`. Novo treinamento depende de dados válidos novos, e não de repetir o mesmo dataset. Banco, Markdown e pesos ativos foram preservados.

### Correção local da fila — 31/10/2026

Após a instalação, foram encontradas imagens de referência sem arquivo de rótulos. A montagem do dataset falhava antes de criar um job e deixava os pedidos indefinidamente como “Na fila”. O worker agora ignora pares incompletos (sem convertê-los em imagens negativas), mantém replay e validação anotados, consolida pedidos genéricos repetidos por modelo, prioriza treinos solicitados sobre a verificação de quadros pendentes e registra estados de preparação, falha e diagnóstico. Solicitações interrompidas durante a preparação voltam à fila ao reiniciar o serviço.

Validação inicial da 0.5.1: 35 testes Python, build do frontend, cinco testes de geometria e cinco testes de UI aprovados. O MSI foi instalado e o worker retomou pedidos persistidos. A 0.5.2 complementa essa correção ao consolidar pedidos elegíveis ligados a amostras. As evidências da instalação atual estão na seção “Consolidação de solicitações ligadas a amostras” acima. Isso corrige fila e diagnóstico, não demonstra melhora de precisão nem autoriza ativar candidatas sem avaliação.

## Uso

- **Aprendizado autônomo** seleciona imagens locais da câmera, verifica rótulos e agenda ciclos de treino de YOLO26s e YOLO26x sem revisão humana obrigatória. Pode ser pausado pelo painel.
- **Treinar contexto agora** registra solicitações para os dois modelos. O processamento respeita recursos, verificação e exemplos novos; o clique não garante ativação imediata.
- **Pausar e revisar quadro** encerra a câmera e congela o último quadro analisado. Desenhe/corrija caixas e informe o nome, por exemplo gaveteiro. **Salvar revisão** apenas persiste a revisão. **Incorporar marcação e treinar agora** salva primeiro, incorpora e solicita treino s/x, com recibos distintos em caso de falha parcial.
- Em revisão parcial, somente caixas humanas são confirmadas; o restante precisa de verificação automática. Sugestões do detector não viram rótulos humanos silenciosamente. Se a verificação for inconclusiva, o pedido é bloqueado com indicação visível.
- A opção de revisão completa confirma todas as caixas e a cobertura da imagem. Não marcá-la se faltam objetos ou há sugestões erradas. Uma classe humana nova pode ser treinada com a própria amostra marcada; a avaliação nessa imagem é apenas um teste de funcionamento, não comprova generalização.

## Arquitetura e processamento

Tauri/Rust + React → JSONL → engine de inferência → processo CPU de aprendizado separado. ONNX Runtime para vídeo, PyTorch/Ultralytics para treino, OWLv2 para investigação textual, ByteTrack e duas vistas para filtragem temporal/geométrica. Sem HTTP, Docker, CUDA, upload de quadros ou APIs pagas.

O maior detector instalado/suportado, atualmente YOLO26x, é pré-carregado na inicialização; a câmera não abre sozinha. A detecção ao vivo usa YOLO26s original ou sua versão adaptada aprovada. Análise estática pode usar x adaptado. Original, ativa e anterior permanecem preservados. Catálogos por modelo mantêm IDs já existentes, acrescentando conceitos sem reordenar classes.

Coleta no máximo a cada 3 s; filtros de desfoque, exposição, duplicação e limites de 3.000 exemplos/1 GB. Uma nova sessão de coleta começa a cada 120 s ou após interrupção. O ciclo automático tenta treinar s/x quando há ao menos quatro exemplos verificados novos desde o ciclo anterior e passou ao menos um minuto; isso não garante diversidade nem independência estatística. Classes novas e promoção continuam sujeitas aos requisitos de evidência abaixo.

Processo em prioridade reduzida, afinidade limitada e treinamento/avaliação configurados para uma thread. RAM disponível não é pré-requisito para iniciar: permanecem os limites de CPU abaixo de 85% e mais de 8 GB livres em disco. Durante a execução, o treino cede tempo entre lotes e pausa cooperativamente se a memória disponível cair abaixo de 3 GB, a latência sustentada passar de 3 s, o usuário pausar ou o ciclo alcançar 30 min. Portanto, o worker pode começar com pouca RAM e pausar no primeiro limite crítico; isso não garante conclusão nem impede falha de alocação do sistema operacional. Não é atualização de pesos por quadro nem garantia de tempo real rígido.

Treino inicial: uma época, imagem 320, batch 1, SGD lr 0,0005, primeiras 22 camadas congeladas; pesos reais da parte treinável são ajustados. Hashes antes/depois registram alteração. Perdas não finitas e pesos inválidos impedem adoção. Checkpoint pausado fornece warm start; não há promessa de retomar exatamente o mesmo lote/estado do otimizador.

Fila persistente por projeto e modelo, deduplicação de pedidos em andamento, recuperação após reinício e prioridade para revisões humanas opcionais. Excluir projeto pausa seu aprendizado antes de remover o projeto; amostras históricas são preservadas e não transferidas silenciosamente para outro escopo.

## Contexto de ambiente

Hipóteses iniciais: quarto, sala, cozinha, escritório ou desconhecido. Evidências estáveis acumulam com decaimento temporal e expiram; lacunas de captura reiniciam a hipótese. Os escores são suporte heurístico, **não probabilidades calibradas**.

Cama/televisão podem sugerir quarto; isso prioriza consultas como guarda-roupa, gaveteiro, armário, janela, porta e caixa de som ao OWLv2. Sala, cozinha e escritório têm consultas próprias, incluindo power bank, multímetro e armário de ferramentas no contexto de escritório. O vocabulário local também cobre sinônimos em português para caixa de som, bateria externa/powerbank, armários, janela, porta e multímetro, além de objetos de eletrônica e oficina. A hipótese fica visível na tela. Não altera a confiança visual, não cria caixas e não fornece rótulo verdadeiro por expectativa. As consultas são isoladas por projeto, limitadas em quantidade e expiram se o contexto não for recente. O perfil não identifica pessoas nem é uma reconstrução geométrica do cômodo.

O vocabulário é uma lista curada local para consultas open-vocabulary, não uma ontologia completa nem uma garantia de reconhecimento. OWLv2 investiga nomes/frases na imagem; COCO continua limitado às suas 80 classes e não contém necessariamente objetos específicos como multímetros. Rótulos humanos são canonicalizados por alias. Ao particionar por sessão, uma classe nova que só apareça na sessão reservada para validação é mantida no treino; a avaliação das classes existentes usa a referência separada.

## Dataset, avaliação e ativação

- Até 512 exemplos por ciclo. Sessão local de validação escolhida pela cronologia, com exclusão de vizinhos a menos de 30 s da fronteira. Assinatura do dataset considera imagens, rótulos, modelo e versão da divisão.
- Referência pública em três partes: índices pares para replay; índices 1 módulo 4 para validação quando não há sessão local; índices 3 módulo 4 para teste de referência. Conjuntos não se sobrepõem no ajuste atual. A referência é pequena e pode pertencer aos dados de pré-treino: não comprova generalização ao mundo real.
- Promoção integral mantém o critério de sessão local separada com pelo menos oito exemplos, alteração real dos pesos e critérios de mAP/AP. Classe nova requer pelo menos vinte exemplos em três sessões, cinco deles na validação. Os limites de referência e de regressão das classes antigas não foram reduzidos.
- Uma classe nova marcada por uma pessoa pode ser servida como complemento provisório quando o peso mudou e o AP da própria marcação de treino for pelo menos 0,50. Esse AP é um smoke test *in-sample*, não validação independente. O complemento só fornece as classes novas; o detector anterior continua responsável pelas classes existentes. A interface avisa que a generalização não foi comprovada. Novas sessões anotadas ainda são necessárias para promoção integral.
- Critérios integrais: referência sem queda maior que 0,005, AP por classe observada sem queda maior que 0,02 e ganho local de pelo menos 0,01. Não contornar uma regressão global ativando a candidata inteira; isolar a saída das classes novas.
- Métricas locais podem conter pseudorrótulos e são medidas substitutas. Confiança, estabilidade e perda menor não comprovam precisão melhor. Métricas são medidas antes/depois, não ajustadas manualmente.
- Candidatas aprovadas são exportadas para ONNX 640, verificadas quanto a formato, finitude e hashes, e disponibilizadas por ponteiro atômico. O engine aquece antes de trocar; falha técnica restaura anterior/original. Retenção protege ambos os modelos e versões anteriores.
- Nenhuma garantia de melhora a cada ciclo ou de reconhecimento de qualquer classe nova. Não há monitoramento independente da precisão real que identifique toda regressão após adoção.

## Diagnóstico da revisão da powerbank — 31/10/2026

A revisão humana estava salva, mas a única amostra de `Powerbank` era atribuída à sessão de validação e havia **zero imagens da classe no treino**. O AP local de 69,65% visto numa candidata YOLO26s vinha dessa única imagem reservada e, portanto, não era evidência independente de aprendizado. A candidata caiu de 59,33% para 43,81% na referência. YOLO26x caiu de 69,94% para 58,03% e teve AP local 0,00%. As quedas são relevantes; não justificam promover o modelo inteiro.

A correção de código em desenvolvimento canonicaliza `Powerbank` para `power bank`, treina com a imagem humana em vez de deixá-la somente na validação e permite, se o AP *in-sample* for suficiente, um complemento de classes que não substitui o detector-base. A mudança ainda precisa ser empacotada/instalada e o candidato resultante precisa ser medido; isso não afirma que a câmera já reconheça a powerbank nem que a classe generalize.

## Evidências e limites

Consultar [entrega 0.5.0](entrega-0.5.0.md) para resultados atuais. Ensaios técnicos em dados públicos/sintéticos não medem qualidade do gaveteiro real, nem FPS de câmera. Os modelos dos ensaios ficam fora das versões ativas. Para conceitos e fontes, consultar [análise acadêmica](conceitos-matematicos-aplicados.md).
