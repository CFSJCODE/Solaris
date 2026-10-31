# Trabalhar no SOLARIS

Antes de mudanças substantivas, consulte AGENTS.md, README.md, MEMORY.md e DECISOES.md. Leia o design system da pasta superior para alterações de interface. Quando uma decisão mudar, registre a mudança e o estado de validação, sem copiar transcrições, credenciais ou arquivos inteiros.

Preserve alterações locais e bancos existentes. Não reintroduza o backend HTTP legado. Não faça commit, push, merge, instalação sobre o aplicativo em uso, chamadas pagas ou treino real sem autorização correspondente.

## Validação

- Frontend: `npm --prefix frontend run build`.
- Revisão gráfica: `npm --prefix frontend run test:annotations`; testes de UI `npm --prefix frontend run test:vision-ui` usam Edge headless, câmera por canvas e IPC simulado, sem dados reais ou API paga.
- Rust/banco/memória: `cargo test --lib --manifest-path src-tauri/Cargo.toml`.
- Engine: `python-engine/.venv/Scripts/python.exe -m unittest discover -s python-engine/tests -v`.
- Build instalado: `scripts/build.ps1`; o processo gera o MSI e não instala.
- Runtime de aprendizado: `scripts/setup_learning.py`, em ambiente separado Python 3.10/CPU. Executa ensaio técnico antes de habilitar o serviço. Não incorporar PyTorch ao engine do chat.
- Integração de aprendizado: `storage/learning-runtime/Scripts/python.exe scripts/check_learning_integration.py <engine.exe>`, com armazenamento isolado; valida pré-carregamento, seleção do detector ao vivo, coleta, pausa e encerramento.
- Treino de ensaio e checkpoint: `scripts/benchmark_learning.py` e `scripts/check_learning_training.py`. São testes técnicos com dados pequenos; não ativar suas candidatas nem apresentar suas métricas como generalização.
- Testes de interface usam armazenamento separado. A variável SOLARIS_TEST_DATA_DIR só é respeitada em builds debug.

Memória automática é uma classificação feita pelo modelo e pode falhar. Testes de protocolo demonstram separação e persistência, não garantem que o modelo reconhecerá toda decisão. Mantenha edição, histórico e indicação visível de atualizações.

Treinamento autônomo autorizado nesta implementação deve ter YOLO26s e YOLO26x como alvos. Preservar original, ativa e anterior, hashes e referências fora do treino. Não tratar rótulos automáticos como verdade humana. Não relaxar os critérios da promoção integral: uma classe nova ensinada por revisão humana pode ser servida somente como complemento provisório, usando apenas suas saídas e preservando o detector-base para as classes antigas; um AP medido nas mesmas marcações de treino não comprova generalização. Limpeza automática restringe-se aos artefatos gerados em learning/runs, learning/datasets e learning/samples; validar caminhos absolutos antes de remoções recursivas.
