> Atualização de continuidade em 31/10/2026: a decisão mais recente inclui treino de **s e x**, mas essa extensão está incompleta. Consulte [roteiro de retomada](continuidade-2026-10-31.md) e [análise dos materiais](conceitos-matematicos-aplicados.md). A versão instalada 0.4.1 não inclui o novo botão de incorporar/treinar agora. Descrições abaixo de treino exclusivamente x correspondem à entrega anterior.

# Aprendizado autônomo local

Estado em 30/10/2026: implementado e instalado no SOLARIS 0.4.0. 23 testes Python, 9 Rust, build React e integração real do executável instalado aprovados. Ainda não há treino de adaptação aprovado com imagens da câmera do usuário. A janela instalada abriu com os dados preservados; GetCursorPos/acesso negado impediu a navegação automatizada ao painel novo.

Decisão do responsável em 30/10/2026: seleção, rotulagem, treinamento, avaliação e ativação sem revisão humana obrigatória. O modelo treinado é sempre YOLO26x. Um modelo menor pode executar a câmera. O original YOLO26x continua pré-carregado e preservado.

## Componentes

- Aplicação: Tauri/Rust e React, comunicação JSON Lines com o engine existente.
- Inferência: ONNX Runtime CPU. YOLO26n e YOLO26s exportados e medidos; escolha inicial YOLO26s.
- Treinamento: Python 3.10 separado, PyTorch 2.10 CPU e Ultralytics 8.4.194. Não embutir PyTorch no engine do chat.
- Professores: YOLO26x original, duas vistas espelhadas; OWLv2 base patch16 ensemble para vocabulário adicional. Snapshot imutável e execução offline após preparação.
- ByteTrack: acompanha as observações selecionadas no serviço de verificação. O rastreador temporal existente permanece no vídeo ao vivo; não alegar comparação de qualidade entre os dois sem vídeo anotado.
- SQLite independente em `storage/learning/learning.sqlite3`, imagens selecionadas no disco, checksums SHA-256 e manifestos JSON. Não altera o esquema de conversas.

## Ciclo

1. Com detecção ao vivo e aprendizado ativo, selecionar no máximo um quadro a cada dez segundos. Rejeitar desfoque, exposição extrema e assinaturas visuais próximas das últimas 256 observações do projeto.
2. Persistir JPEG e origem do detector. Limites globais de 3.000 exemplos ou 1 GB. Não grava vídeo inteiro nem envia imagens a APIs.
3. Sem detecção em nenhum projeto há 45 segundos, computador sem entrada há dois minutos, CPU abaixo de 60%, pelo menos 6 GB de RAM livres e 8 GB de disco livres: verificar exemplos pendentes.
4. Filtrar concordância geométrica e de classe em duas vistas. Mala, bolsa e mochila exigem também concordância do OWLv2. Consultas incluem classes observadas e vocabulário adicional. Incertezas ficam preservadas fora do treino. Isso não é verdade humana.
5. Depois de 128 exemplos utilizáveis em três sessões, preparar dataset versionado. Uma pausa superior a dois minutos inicia uma sessão de coleta nova. Sessões são separadas entre treino e validação local.
6. Treinar YOLO26x, batch 1, 320 px, três épocas, SGD, primeiras 22 camadas congeladas. Original e ativa preservados. Pausas no fim de um lote salvam checkpoint; recuperação é warm start dos pesos, sem promessa de reconstruir a posição exata do lote.
7. Avaliar referências COCO128 separadas (64 imagens) e validação local de rótulos automáticos. As outras 64 referências entram como replay no treino. A referência é pequena: não é avaliação abrangente de todas as classes.
8. Exigir mAP conhecida sem queda maior que 0,005, AP de cada classe observada sem queda maior que 0,02 e melhora de pelo menos 0,01 na validação local automática. Confiança e loss não aprovam versão.
9. Exportar ONNX 640 end-to-end, verificar entrada/saída e números finitos, registrar hashes e trocar manifesto atomicamente. Engine aquece a candidata antes de usá-la. Falhas de carga revertem automaticamente para a anterior/original.

## Classes novas

Vocabulário inicial adicional: caixa de ferramentas, capacete de segurança, mala com rodas, caixa de papelão, furadeira, chave de fenda, alicate, filtro de linha, fone de ouvido e bebedouro. Consultas internas em inglês, rótulos exibidos em português. Preservar IDs COCO 0–79; classes extras são acrescentadas ao catálogo do dataset, nunca substituem IDs antigos.

Uma classe precisa de pelo menos vinte exemplos de três sessões para entrar no catálogo. O sistema não descobre nomes arbitrários de qualquer objeto. OWLv2 depende desse vocabulário inicial; conceitos fora dele permanecem sem identificação. Melhora na validação local automática é uma medida substituta, não prova independente de precisão em classes novas.

## Execução e limites

`scripts/setup_learning.py` cria ambiente separado e prepara os assets. `scripts/benchmark_learning.py` executa ensaio real de treinamento/exportação antes de marcar o runtime como validado. Depois disso, o engine inicia o serviço sozinho, em prioridade reduzida e afinidade limitada a quatro processadores lógicos. O serviço termina se o engine sair; o watchdog evita treinamento órfão.

Há limite de 12 GB para datasets e treinos. A retenção automática limpa experimentos antigos e exemplos vencidos, preservando versão ativa, anterior, checkpoints recuperáveis e duas experiências recentes. Métricas e manifestos permanecem no histórico. Se apenas os itens protegidos excederem a capacidade, o serviço informa e aguarda espaço. Checkpoints e rótulos são locais. Pausar aprendizado preserva dados. O limite de trinta minutos pausa um ciclo ao fim do lote.

O próprio detector não decide que uma previsão sua é correta. A avaliação independente cobre somente as classes presentes na referência. Não há garantia de melhora a cada treino. Não há monitoramento independente da precisão no mundo real; a reversão automática desta fase cobre falhas técnicas de ativação.

## Evidência local inicial

Ryzen 5 4600G, 32 GB, sem GPU. Inferência sintética 640, cinco medições depois do aquecimento, três threads: mediana YOLO26n 44,8 ms; YOLO26s 136,3 ms. Exclui câmera, JPEG e IPC.

Professores em uma imagem: 18,7–19,6 s incluindo carregamento e duas vistas, quatro caixas aceitas. Treino técnico YOLO26x com duas imagens/uma época: 7,2–9,0 s, aproximadamente 3,4 GB RSS observado no callback; não é pico garantido. Segundo ensaio expandiu o catálogo para 81 classes, conferiu APIs de avaliação e exportação ONNX `[1,300,6]`. Isso não prova identificação da classe adicional. Treino/validação do ensaio usam as mesmas duas imagens: não mede generalização. A candidata do ensaio não foi ativada.

Na segunda medição, as medianas sintéticas foram 41,6 ms (n) e 154,8 ms (s). O motor foi copiado e validado em AppData/com.cfsjcode.solaris/storage/learning-runtime, independente da pasta de desenvolvimento. Pesos e snapshot OWLv2 também ficam nos dados do aplicativo. O MSI distribui o aplicativo/engine; a preparação adicional instala esse runtime local separadamente.
