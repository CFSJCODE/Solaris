> Atualização 0.5.0: além de salvar, é possível **Incorporar marcação e treinar agora**. Consulte [aprendizado atual](aprendizado-autonomo.md) e [validação da entrega](entrega-0.5.0.md). A seção histórica abaixo sobre não importar revisões ao treino descreve a versão 0.4.1.

# Revisar e nomear objetos em um quadro

Solicitado pelo responsável em 31/10/2026: pausar a captura ao vivo e desenhar marcações com nome livre, seguindo a interação de revisão do DroneCamp e preservando a identidade SOLARIS.

1. Abra a câmera e inicie a detecção ao vivo.
2. Clique em **Pausar e revisar quadro**. O app usa o último quadro efetivamente analisado, interrompe o loop e encerra os tracks da câmera. Uma inferência já enviada pode terminar no engine, mas seu retorno não substitui a revisão.
3. Em **Desenhar marcação**, arraste do primeiro ao segundo canto do objeto. O campo **O que é este objeto?** recebe foco. Escreva, por exemplo, `mala` ou `caixa de ferramentas`.
4. Acrescente uma descrição opcional. **Selecionar e ajustar** permite mover a caixa e arrastar seus cantos. A lista de objetos também seleciona a caixa. **Esc** cancela um desenho em andamento; **Desfazer marcação** recupera a última mudança estrutural.
5. Clique em **Salvar revisão**. Caixas sem nome impedem a gravação. O registro conserva a imagem, dimensões, coordenadas nos pixels da imagem, nomes, observações e origem humana das correções.
6. **Retomar câmera ao vivo** pede uma nova captura ao navegador e retoma o loop quando o modelo está carregado. O rascunho é mantido enquanto a câmera está em uso; revisar outro quadro substitui o rascunho anterior. Salve antes de trocar de quadro ou sair da tela. A troca de projeto limpa o quadro anterior para evitar associação errada.

**Capturar quadro**, mesmo sem detecção, também desliga a câmera e abre uma revisão vazia. Imagens PNG/JPEG podem receber marcações sem rodar o detector. A revisão é opcional; o aprendizado autônomo continua disponível sem seleção humana obrigatória.

## Persistência e limites

O comando Tauri existente `save_vision_sample` guarda o payload JSON em `vision_samples`, isolado por projeto. A nova revisão usa schema_version 2 e campos opcionais `source`/`description` em cada caixa; registros antigos são preservados. Nome livre não recebe um ID COCO inventado. Uma correção manual não é apresentada como confiança de inferência.

Salvar revisão não treina pesos imediatamente. Estes registros humanos ainda não são importados automaticamente pelo serviço de treinamento, que mantém seu dataset próprio. Não afirmar que desenhar ou escrever um nome já ensinou uma classe nova ao YOLO.

## Validação

- `npm --prefix frontend run build` verifica TypeScript e distribuição.
- `npm --prefix frontend run test:annotations` cobre escala, desenhos invertidos, limites, movimento e redimensionamento de caixas pequenas nas bordas.
- Em frontend, `npm run test:vision-ui`: três testes no Edge headless com vídeo gerado por canvas e comandos Tauri simulados. Cobrem encerramento real do MediaStream simulado, parada de inferências, desenho/nome/descrição/payload, remoção/desfazer, movimento/cantos, Escape, retomada e troca de projeto.

Os testes do navegador não comprovam acesso à webcam física nem gravação por IPC nativo; essa distinção deve aparecer no registro de entrega.

Conferência adicional da entrega 0.4.1 em 31/10/2026: instalado MSI e preservação dos dados verificada. Na janela instalada, abertura da câmera, detecção, Pausar e revisar, desenho e rótulo escrito conferidos. A captura ficou interrompida e a revisão aberta. Não foi salva uma revisão de teste na base real.
