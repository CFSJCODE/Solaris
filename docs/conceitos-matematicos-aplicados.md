> Atualização posterior: treino s/x e contexto heurístico foram entregues na [0.5.0](entrega-0.5.0.md). A análise abaixo preserva a distinção entre hipóteses acadêmicas e recursos implementados; fusão probabilística calibrada, PCA e alternativas adicionais continuam propostas.

# Conceitos dos materiais e aplicação ao SOLARIS

Análise documental de 31/10/2026. Objetivo: aproveitar matemática e visão computacional preservando o app Windows CPU, projetos, memória Markdown e engine por pipes. **As propostas deste relatório não são funções já entregues.** A continuação da implementação e suas pendências estão em continuidade-2026-10-31.md.

## Fontes, método e limites

Pasta original: `E:/Acadêmico/Cursos E Extensão Curricular/A MATEMÁTICA POR TRÁS DO MACHINE LEARNING/`. Originais preservados. Referências de páginas abaixo usam **página do PDF, começando em 1**, salvo indicação expressa de página impressa.

| Material fornecido                                  | Exame realizado e limite                                                                                                                                                                 |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| aula-1-slides.pdf                                   | 44 páginas em imagem; OCR local de todas as páginas, com inspeção visual seletiva                                                                                                        |
| aula-2-slides.pdf                                   | 36 páginas em imagem; OCR local de todas; exemplo da perda da p.13 conferido visualmente                                                                                                 |
| aula-3-slides.pdf                                   | 23 páginas em imagem; OCR local de todas; diagramas não são interpretáveis apenas pelo texto OCR                                                                                         |
| MATHEMATICS FOR MACHINE LEARNING.pdf                | 417 páginas; extração textual e consulta direcionada aos capítulos pertinentes; Deisenroth, Faisal e Ong, cópia com indicação draft 2024-01-15                                           |
| Why Machines Learn PDF.pdf                          | 151 páginas; extração textual e seções pertinentes; **resumo Bookey**, identificado na p.2, não o livro integral de Anil Ananthaswamy                                                    |
| NotaAula01_Matematica_Machine_Learning_Expandida.md | Nota expandida: conteúdo da aula e complementos didáticos precisam ser distinguidos                                                                                                      |
| NotaAula01MatematicaML_Transcricao.txt              | Notas organizadas a partir de quatro páginas manuscritas; não transcrição integral da aula                                                                                               |
| NotaAula02_Matematica_Machine_Learning_Expandida.md | Nota expandida baseada também em legendas automáticas; complementos não são automaticamente falas do professor                                                                           |
| visao-computacional-main.zip                        | Inventário de 116 entradas; leitura estática das células-fonte de 20 notebooks e textos pequenos .py/.md/.toml; saídas, modelos e vídeos não executados; ZIP interno apenas inventariado |

Cache local ignorado pelo Git em storage/document-analysis: inventory.json, textos extraídos, OCR por página, zip-text.json e imagens selecionadas. Ferramentas documentais foram instaladas somente em storage/document-tools; não são dependências do produto. Não redistribuir livros, cache integral ou imagens das aulas no repositório. OCR pode errar símbolos e fórmulas; consultar a página original em caso de dúvida. A análise foi dirigida ao SOLARIS, não revisão matemática integral das 417 páginas do livro.

### Cuidados de fidelidade às fontes

- Aula 2, p.8–13: usa perda e²; com saída 0,6 e alvo 1, perda = 0,16. A nota expandida usa a convenção ½e² e apresenta 0,08, com outra taxa de aprendizado. Ambas podem descrever o mesmo passo se os fatores forem coerentes. Não comparar losses entre convenções como se fossem a mesma escala.
- As notas da aula 1 registram uma linha (5,3) → 8 incompatível com a regra x₁+2x₂; a própria nota aponta a ambiguidade. Não transformar reconstrução/transcrição em prova de erro do professor. O exemplo novo da p.12 dos slides usa (5,2) → 9.
- A agenda dos slides menciona quatro aulas; só três conjuntos de slides foram fornecidos. Não inventar conteúdo da quarta.
- O resumo Bookey é fonte secundária; passagens sobre grokking/generalização não são garantia de que treinar mais melhorará o detector.

## Conceitos extraídos e aplicação proposta

| Conceito e fonte                                                                         | Aplicação pertinente ao SOLARIS                                                                                             | Limite / estado                                                                                             |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Representação vetorial, features e parâmetros — aula 1 p.8, 14, 30–41                    | Manter contratos de tensores, normalização, dimensões e catálogo entre PyTorch e ONNX; registrar configuração junto ao hash | Rede convolucional não equivale à regra linear dos exemplos didáticos; contratos já existem, ampliar testes |
| Treino versus inferência — aula 1 p.34                                                   | Separar serviço ONNX ativo do processo que altera candidata PyTorch                                                         | Arquitetura já adotada; extensão s+x incompleta                                                             |
| Gradiente e regra da cadeia — aula 2 p.5–16; MML §5.2, §5.6, §7.1                        | Usar autograd/otimizador existentes, congelamento parcial e taxa pequena; registrar pesos antes/depois                      | Não escrever backprop manual nem supor que uma época generaliza                                             |
| Risco empírico e generalização — aula 1 p.13, 39; aula 2 p.17; MML §8.2                  | Separar sessões/tempo/cenas; comparar candidata e ativa no mesmo conjunto e preservar teste independente                    | Prioridade imediata; sessões consecutivas podem vazar contexto                                              |
| Bayes e taxas-base — aula 2 p.18–36; MML §6.3–6.4                                        | Contexto quarto/sala como prior limitado; combinar com evidência visual e possibilidade desconhecida                        | Proposta, não implementada como semântica de ambiente                                                       |
| MLE, MAP e regularização — aula 2 p.34–35; MML §8.3–8.4                                  | Restringir deriva, usar referência das classes antigas e treino gradual                                                     | MAP = máximo a posteriori; mAP = média da precisão média, outro conceito                                    |
| Convolução e campos receptivos — aula 3 p.6–7, 19–23                                     | Melhorar pré-processamento, preservar geometria/letterbox e mapear caixas para o quadro original                            | Filtro de borda não substitui detector e não ensina nome de classe                                          |
| Qualidade visual, HSV, histogramas, morfologia — notebooks do ZIP                        | Rejeitar desfoque/exposição ruim e reduzir exemplos repetidos; diagnosticar iluminação                                      | Proposta complementar; equalização agressiva pode distorcer distribuição do modelo                          |
| Rastreamento e consistência temporal — projeto de contagem/DeepSORT do ZIP               | Reunir vistas do mesmo objeto e diversidade temporal; comparar com ByteTrack atual                                          | Rastreador não certifica o nome; DeepSORT adiciona custo de reidentificação                                 |
| PCA e modelos de mistura — MML caps.10–11                                                | Opcional: compactar descritores e explorar agrupamentos para selecionar amostras diversas                                   | Não nomeia classe nova sozinho; adiar até haver descritores/dados e comparação                              |
| Árvores/Naive Bayes — notas expandidas e aula 2                                          | Baseline leve sobre estatísticas de cena, se existir conjunto rotulado confiável                                            | Dependência entre features pode duplicar evidência; não substituir YOLO sem avaliação                       |
| Incerteza, calibração e mudança de domínio — complementos das notas; MML model selection | Mostrar desconhecido, medir calibração em dados adequados e detectar mudança de ambiente                                    | Proposta; score 0,95 não garante 95% de acerto                                                              |

### Referências direcionadas do livro MML

- Gradientes: §5.2, p.146 impressa / PDF152; autodiferenciação: §5.6, p.159 / PDF165; Taylor: §5.8, p.165 / PDF171.
- Bayes: §6.3, p.183 / PDF189 e seguintes; independência: §6.4, p.186 / PDF192.
- Gradiente descendente: §7.1, p.227 / PDF233; minibatch/SGD: p.232 / PDF238.
- Risco empírico: §8.2, p.258 / PDF264; regularização/validação: PDF266–268; estimação: §8.3, p.265 / PDF271.
- Modelagem probabilística: §8.4, p.272 / PDF278; modelos gráficos: §8.5, p.278 / PDF284; seleção: §8.6, p.283 / PDF289.
- PCA: cap.10, p.317 / PDF323; misturas gaussianas: cap.11, p.348 / PDF354. São referências de consulta, não licença para mudar a arquitetura inteira.

## Como usar contexto de ambiente sem confirmar os próprios erros

Exemplo: a câmera observa cama e televisão de forma estável; pode aumentar a hipótese de quarto. O sistema pode então priorizar investigação de guarda-roupa/gaveteiro em regiões com evidência visual. Não deve desenhar um guarda-roupa porque um quarto “deveria” ter um, nem alterar o rótulo de uma mala só por sua frequência naquele ambiente.

Arquitetura proposta, posterior à conclusão do treino atual:

1. **Evidência visual:** conservar classe, caixa, score original, modelo, instante e track. Não substituir o score original pelo contextual.
2. **Perfil de cena por projeto/câmera:** hipóteses e contagens com decaimento temporal, estado desconhecido e reinício/segmentação quando houver mudança relevante. Não assumir que toda conversa do projeto corresponde ao mesmo cômodo.
3. **Prior contextual limitado:** combinar hipótese da cena com evidência sem contar a mesma observação duas vezes. Preferir orientar consultas do professor e seleção de amostras antes de alterar decisões finais.
4. **Verificação e diversidade:** consistência em transformações/vistas, amostras não redundantes, comparação de modelos, etiquetas humanas opcionais. Guardar origem e incerteza dos autorrótulos.
5. **Treino candidato:** ajustar s/x em ciclos limitados com referência das classes antigas. Registrar parâmetros, dados e hashes. Não treinar a rede x por quadro na CPU.
6. **Avaliação e ativação:** métricas separadas por classe/ambiente, comparação com modelo atual e teste independente. Falta de evidência mantém candidata pendente. Disponibilizar reversão.

Uma futura fusão probabilística pode trabalhar em log-probabilidades com peso contextual limitado e calibrado. Não multiplicar scores YOLO arbitrários por frequências e chamar isso de posterior: scores não são probabilidades calibradas e as observações não são independentes. Comparar visual puro versus visual+contexto, incluindo cômodos atípicos e mudança de cena.

## Aprendizado autônomo: interpretação correta

O pedido de “o próprio modelo se corrigir” é um ciclo de **autotreinamento/semi-supervisão com pseudorrótulos e consistência**, não aprendizado sem nenhum sinal de supervisão. Modelos pré-treinados e professores trazem supervisão anterior. Agrupamento não supervisionado ajuda a selecionar diversidade, mas não descobre sozinho que um grupo se chama gaveteiro.

Risco principal: realimentação de erro. Professor maior e OWLv2 também podem errar; duas respostas semelhantes não equivalem a verdade independente. Reduzir risco com diversidade, abstenção, filtros de qualidade, retenção de referências e avaliação independente. Melhorar loss de treino não significa melhorar detecção real.

Replay de exemplos antigos, regularização, distilação ou atualização de professor por média móvel são técnicas candidatas para pesquisar/comparar, **não componentes já demonstrados neste projeto nem necessariamente ensinados nos anexos**. Só acrescentar se houver hipótese testável e orçamento CPU. Não implantar Hessiana completa ou covariância de todos os pesos: custo quadrático é inadequado ao hardware.

## O que não importar dos materiais

- Exemplos AWS/Lambda/API/Docker e downloads dos notebooks não justificam alterar a arquitetura local nem enviar imagens à nuvem.
- Não executar scripts, notebooks, modelos Caffe/PyTorch ou dependências do ZIP sem revisão, integridade e necessidade concreta.
- Distância em notebook com pixel_per_meter = 10 é uma hipótese de escala, não distância física calibrada em câmera arbitrária. Metros exigem calibração/geometria/depth adequados.
- Detector Caffe de faces demonstra localização, não reconhecimento de identidade. Não acrescentar biometria implicitamente.
- Notebook morfológico marcado INCOMPLETO e checklist de contornos não são implementações prontas. Pesos pré-treinados e vídeos do pacote não são dataset validado do SOLARIS.
- Hebb e referências neurocientíficas são inspiração histórica, não justificativa para aumentar confiança de toda detecção repetida.
- Perceptron converge sob hipóteses específicas de separabilidade; isso não prova convergência ou acerto do detector profundo em ambiente novo.

## Prioridades de aplicação

**Primeiro:** finalizar incorporação/treino s+x com testes, partição de dados e medição real de recursos. **Depois:** qualidade/diversidade, rastreabilidade e métricas por classe; contexto probabilístico limitado com teste comparativo. **Por último:** agrupamento/PCA, alternativas de rastreamento e técnicas adicionais de aprendizagem contínua, se os resultados justificarem.

Critério de sucesso: detecções corretas em imagens futuras e ambientes variados, preservando classes antigas e responsividade. Contagem de ciclos, maior confiança, perda menor e maior estabilidade são diagnósticos auxiliares, não substitutos dessa evidência.
