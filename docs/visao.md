> **Estado atual: 0.5.0 instalada**, com incorporação e treino s/x, contexto heurístico e revisão de quadros. Consulte [ciclo vigente](aprendizado-autonomo.md) e [validação](entrega-0.5.0.md). O restante preserva o histórico de versões anteriores.

# Visão local em CPU

**Estado vigente: SOLARIS 0.4.1.** Consulte [revisão gráfica de quadros](revisao-quadros.md) e [aprendizado autônomo](aprendizado-autonomo.md): YOLO26x pré-carregado, YOLO26s ao vivo, coleta seletiva, treino YOLO26x e avaliação automática. As seções iniciais abaixo registram a implementação anterior de captura manual/YOLOv8n; foram superadas pelas atualizações descritas ao final e pelos documentos atuais.

O aplicativo usa YOLOv8n via ONNX Runtime CPU, carregado somente na primeira detecção. Não usa CUDA, PyTorch em runtime nem envia imagens aos provedores do chat. A câmera abre somente por ação do usuário; cada captura é analisada sob demanda, sem fila de vídeo.

## Modelo usado no build

- Origem dos pesos: [Ultralytics YOLOv8](https://huggingface.co/Ultralytics/YOLOv8).
- Exportação ONNX: [unileon-robotics/YOLO8-ONNX](https://huggingface.co/unileon-robotics/YOLO8-ONNX), revisão `66e5888954d3454da709847e77b36df31f756aa9`, arquivo `dynamic/yolov8n.onnx`.
- SHA-256: `01d7aa04e4f6a21784ec5dee4b8377d4bd83bec2b85078c99815ec3d3093d49e`.
- Entrada RGB float32 NCHW, batch 1; saída bruta `[1,84,N]`, classes COCO, sem NMS no grafo. Modelos pose/segmentação/classificação não são compatíveis.
- O detector usa entrada 320 px para modelos dinâmicos, letterbox, confiança mínima 0,35 e NMS por classe de 0,45. Modelos estáticos quadrados de até 640 px também são aceitos.
- O repositório de exportação informa a origem Ultralytics e remete aos seus termos. Preserve os [termos dos pesos](https://www.ultralytics.com/license) ao distribuir; a licença MIT do código SOLARIS não altera a licença dos modelos.

`scripts/prepare_vision.py` baixa a revisão fixa e verifica o checksum. Os pesos ficam em `storage/models/yolov8n.onnx` (ignorado pelo Git) e são incluídos no engine pelo PyInstaller. Não há download na abertura do aplicativo. Uma cópia em `SOLARIS_STORAGE/models/yolov8n.onnx` tem precedência sobre o modelo empacotado.

## Uso e revisão

1. Selecione o projeto na navegação.
2. Abra PNG/JPEG de até 12 MB ou abra a câmera e capture um quadro.
3. Clique em **Detectar objetos**.
4. Corrija classe e coordenadas, remova falsos positivos ou adicione caixas ausentes.
5. Clique em **Salvar revisão**. Imagem e anotações ficam na tabela SQLite `vision_samples`, com projeto, modelo e versão do formato.

As revisões são insumos para trabalho futuro; salvar não inicia treino nem promove modelo. A tela ainda não lista revisões anteriores. A captura é manual; não há promessa de FPS contínuo.

## Validação

- `python-engine/.venv/Scripts/python.exe -m unittest discover -s python-engine/tests -v`
- `cargo test --lib` em `src-tauri` cobre migração e isolamento de memória, além da preservação das revisões ao excluir projeto.
- `npm run build` em `frontend` verifica TypeScript e bundle.

No teste local com a imagem pública `ultralytics/assets/bus.jpg`, a inferência 320 px retornou ônibus e três pessoas. Três execuções mediram 20,0 / 11,6 / 11,4 ms, excluindo carregamento inicial, leitura e IPC. É um teste funcional, não benchmark de câmera ou avaliação de qualidade.

## Atualização 0.3.1 — YOLO26x e câmera contínua

Por decisão do responsável, o maior modelo instalado é pré-carregado na inicialização e fica residente. YOLO26x incluído, origem dos pesos Ultralytics e exportação [prithivMLmods/YOLO26-ONNX](https://huggingface.co/prithivMLmods/YOLO26-ONNX), revisão c526dae7a5a5b4f1d79d704903b4406011da2716, arquivo yolo26x/yolo26x.onnx. SHA-256 a879d5b533db9291eeb8ba332f1ef2b7a8f3a10003f35baa1dbdf3be872a3e6f. Tamanho 223.287.525 bytes, entrada [1,3,640,640], saída end-to-end [1,300,6]. Termos dos modelos continuam vinculados à origem Ultralytics.

A câmera funciona continuamente e a inferência é sequencial, sem fila de frames. A câmera só abre por ação do usuário. Todas as classes COCO são traduzidas para pt-BR, preservando os IDs.

Adaptação: associação temporal por classe e sobreposição, estabilidade após três observações, suavização de caixas de alta sobreposição, estatísticas online de posição/tamanho e recorrência. Perfis por projeto persistem em storage/environment; IDs temporais não persistem entre sessões. Imagens não são coletadas continuamente. Perfis inválidos são preservados e geram aviso. Isto não é treinamento dos pesos do detector nem prova de melhora de mAP.

Validação local de imagem pública: ônibus e quatro pessoas; carregamento+aquecimento 1.924 ms; três inferências de 952,1/962,9/918,7 ms. A taxa da webcam deve ser medida na interface em uso real. Evolução dos pesos continua uma fase futura, condicionada a avaliação e rollback automáticos.
