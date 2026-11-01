# Entrega 0.5.0 — registro de validação

Concluída em 31/10/2026: versão 0.5.0 instalada e aberta; dados anteriores preservados. Não houve publicação Git nesta entrega.

## Implementação

Incorporação de revisão persistida com escopo de projeto; fila de treino s/x; retomada após reinício; treino e métricas reais; proteção contra números inválidos; validação cronológica; referência separada de replay/validação/teste; contexto heurístico para consultas do verificador; controle de recursos e recibos em português.

## Validações já concluídas

- 31 testes Python, 10 testes Rust, cinco testes de geometria e cinco fluxos de UI com câmera/IPC simulados aprovados; frontend compilado.
- Protocolo real: pré-carregamento x, inferência s, cinco objetos em imagem pública, coleta, incorporação, pedidos dos dois modelos, pausa e encerramento sem processo órfão.
- Ensaio real dos dois modelos com uma thread, nove imagens de treino (incluindo replay), quatro imagens de validação e quatro de teste de referência: alteração dos pesos confirmada e exportações ONNX [1,300,6] finitas. Modelos não ativados por insuficiência de evidência local. Relatório local: storage/model-cycle-20261031-013055/results.json.
- Tempos nesse ensaio incluindo exportação: aproximadamente 18 s para s e 81 s para x. Não representam duração de treino num dataset de produção nem melhora na câmera real.

## Fila automática e instalação

Fila automática em processo separado e recuperação de solicitação interrompida concluídas: ambos os pedidos terminaram avaliados, com alteração de pesos e sem ativar candidatas. Relatório: storage/learning-queue-20261031-093516/results.json.

Expansão real de catálogo de s e x para 81 classes, preservando IDs antigos e acrescentando chest of drawers/gaveteiro, confirmada com revisão sintética. Nenhuma candidata do ensaio foi ativada. Relatório: storage/learning-queue-20261031-093754/results.json. Isso comprova compatibilidade técnica, não precisão da nova classe.

Engine empacotado aprovado no protocolo real: x pré-carregado, s ao vivo, incorporação e fila s/x, pausa e encerramento sem órfãos. As cinco fontes de visão/treino incluídas no executável correspondem byte a byte ao código final; ausência de .env no pacote verificada. Evidências: storage/engine-0.5.0-integration.log e storage/engine-0.5.0-sources.json.

MSI final gerado: src-tauri/target/release/bundle/msi/Solaris_0.5.0_x64_en-US.msi, **314.347.520 bytes**. Instalação silenciosa sem elevação recusada; instalação com elevação padrão do Windows retornou 0. Executável instalado informa 0.5.0. Engine instalado tem o mesmo hash do validado; comparação do app encontrou somente o marcador Tauri de três bytes UNK/MSI esperado. Evidência: storage/install-0.5.0-verification.json.

Backup consistente criado antes da instalação, incluindo banco de aprendizado e manifestos de versões. Verificação posterior: bancos íntegros, contagens anteriores de conversas/aprendizado preservadas e hashes dos Markdown anteriores inalterados. Ponteiro: storage/update-0.5.0-manifest.txt.

Teste do engine **instalado em Program Files** passou: x pré-carregado, s ao vivo, cinco objetos na imagem pública, coleta, incorporação e pedidos s/x, pausa e encerramento sem órfãos. Evidência: storage/installed-engine-0.5.0-integration.log.

Na janela nativa foram conferidos: modelo x carregado, painel e botões em português, câmera física com s, hipótese contextual escritório e pausa/revisão do último quadro. Observados aproximadamente 2,7–3,0 análises/s e 207–211 ms de fluxo completo, sem treino concorrente nessa medição. Desenho manual abriu campo de nome e botão de incorporação; rascunho de conferência não salvo. Câmera deixada desligada. O clique nativo de incorporação sobre dados reais não foi executado: persistência/isolamento e ciclo de treino foram validados pelos testes de banco/protocolo e UI simulada em dados isolados.

A implementação está instalada; permanecem como limites de evidência a precisão real da classe nova, a generalização ao ambiente e o desempenho em treino concorrente com webcam física. Não apresentar esses pontos como resultados já demonstrados.

## Limites permanentes

Sem prova de melhora real no ambiente do usuário. Contexto é hipótese heurística, não probabilidade calibrada ou fonte de verdade. Treinamento em CPU ocorre em ciclos com pausas, não atualização de toda a rede a cada quadro. Nenhuma chamada paga, envio de imagens ou publicação Git faz parte desta entrega.

## Acompanhamento local da fila — 31/10/2026

Depois da instalação, o banco local mostrava pedidos pendentes sem jobs correspondentes. O log identificou arquivos de rótulos ausentes em duas imagens de referência; a preparação abortava antes de atualizar o pedido, que permanecia na fila. O código-fonte foi corrigido para pular imagens sem rótulos, consolidar pedidos genéricos repetidos, priorizar treino solicitado sobre o backlog de verificação, recuperar preparações interrompidas e exibir falhas com diagnóstico. Testes: 35 Python, build frontend, cinco testes de geometria e cinco de UI aprovados.

Naquele ponto, a correção ainda não tinha sido empacotada. A atualização 0.5.1 foi instalada depois; a consolidação adicional de solicitações por amostra e a validação da instalação atual estão registradas abaixo.

## Atualização 0.5.1 instalada — 31/10/2026

- Instalador: `src-tauri/target/release/bundle/msi/Solaris_0.5.1_x64_en-US.msi`, 314.187.776 bytes (299,63 MiB). Instalação elevada via Windows Installer retornou 0; a versão registrada e o executável instalado são 0.5.1.
- Engine em `C:\Program Files\Solaris\solaris-engine.exe` tem SHA-256 idêntico ao engine do build: `CCBC67B04CF271EA42119A0A34E47E840C7F8067FF3B4F9D7CD5E3F46FB0FF45`.
- Snapshot consistente pré-instalação em `%APPDATA%\com.cfsjcode.solaris\backups\antes-0.5.1-20261031-102852-f7099ed3\manifest.json`. Verificação pós-instalação aprovou integridade SQLite, contagens de conversas/aprendizado não reduzidas e hashes Markdown preservados.
- Aplicativo reaberto e responsivo; engine em execução. O worker retomou pedidos persistidos: a candidata YOLO26s terminou avaliada e foi recusada, sem ativação. Na última checagem, YOLO26x avançava no lote 38/67; outros pedidos seguem pendentes para processamento sequencial. Não afirmar melhoria de precisão nem ativação da candidata.
- Testes antes do empacotamento: 35 Python, build frontend, cinco testes de geometria e cinco testes de UI aprovados. Nenhuma API paga ou publicação Git.

## Atualização 0.5.2 instalada — 31/10/2026

- Instalador `Solaris_0.5.2_x64_en-US.msi`: 314.191.872 bytes (299,64 MiB). Build de frontend, engine PyInstaller e Tauri release concluído; o MSI foi instalado com elevação padrão do Windows e o Windows Installer retornou 0. O executável em `C:\Program Files\Solaris\solaris.exe` informa versão 0.5.2.
- Engine em `C:\Program Files\Solaris\solaris-engine.exe` tem SHA-256 idêntico ao engine compilado: `D709428ECAF807ED0D2B85668F5CFED4383112B56AC6E33291B1DA422C4C3DEC`.
- Snapshot consistente pré-instalação: `%APPDATA%\com.cfsjcode.solaris\backups\antes-0.5.2-20261031-105125-ee9399b3\manifest.json`. Verificação pós-instalação aprovou integridade SQLite, contagens de conversas/aprendizado não reduzidas e hashes Markdown preservados.
- Aplicativo reaberto. O ciclo ativo foi concluído antes da instalação: as candidatas YOLO26s e YOLO26x foram recusadas pela avaliação, sem ativação. Na base após a atualização não havia job ativo nem pedido `queued`: dois pedidos estavam avaliados e quatro bloqueados porque o conjunto já fora processado ou faltavam novos exemplos verificados/diversidade. Esses pedidos não estão aguardando execução; novos dados válidos podem iniciar outro ciclo.
- Antes do empacotamento: 37 testes Python, 10 Rust, build frontend, cinco testes de geometria e cinco de UI aprovados. A instalação e a preservação dos dados foram verificadas. Não há melhora real de precisão comprovada, e nenhum critério de promoção foi flexibilizado.

## Atualização 0.5.3 instalada — 31/10/2026

- Instalador `Solaris_0.5.3_x64_en-US.msi`: 314.200.064 bytes (299,64 MiB). Build de frontend, engine PyInstaller e Tauri release concluído; Windows Installer elevado retornou 0. O executável em `C:\Program Files\Solaris\solaris.exe` informa versão 0.5.3.
- Engine em `C:\Program Files\Solaris\solaris-engine.exe` tem SHA-256 idêntico ao engine compilado: `763C2C255A1C1D8334D091E68A550D466A2C1AC5206C96D4C0C716B465B66933`.
- Snapshot consistente pré-instalação: `%APPDATA%\com.cfsjcode.solaris\backups\antes-0.5.3-20261031-114012-8e5eed87\manifest.json`. Verificação pós-instalação aprovou integridade SQLite, contagens de conversas/aprendizado preservadas e hashes Markdown inalterados.
- A admissão não exige mais um mínimo de RAM; CPU abaixo de 85% e disco livre acima de 8 GB continuam limitando o início. A pausa cooperativa em menos de 3 GB durante o treino foi mantida. Após reabrir, o worker iniciou treino YOLO26x abaixo do antigo limiar de 6 GB e avançava no lote 39/69 na última checagem. A candidata segue em treinamento; não afirmar avaliação ou ativação concluída.
- O vocabulário OWLv2 contextual ampliado também foi incluído no pacote. Testes: 43 Python aprovados; build frontend e MSI concluídos. Sem alegação de melhora de precisão.

## Atualização 0.5.8 instalada — 01/11/2026

- Conteúdo: interface Liquid Glass + Fluent UI 2 com paleta preservada (PR #30, merge `f9ca152`), sobre a 0.5.7 instalada. Branch de release `release/0.5.8`.
- Antes do empacotamento: `test:design` (11), `test:annotations` (5) e build do frontend aprovados. Python e Rust não foram reexecutados nesta release, porque só a interface mudou.
- Instalador `Solaris_0.5.8_x64_en-US.msi`: 326.352.896 bytes (311,23 MiB). SHA-256 do MSI: `E29BF81814F2D5F672AF897923E156F33D420D8F1F9D8332C932175948617BF5`. Log do build e do Windows Installer em `storage/release-0.5.8/`.
- Windows Installer elevado retornou 0; `C:\Program Files\Solaris\solaris.exe` informa 0.5.8. Engine instalado com SHA-256 idêntico ao compilado: `F91B1B173571E0D487F9D0C40E760BED136B9AAE1DF4301AF6C9855721B54DE6`.
- Snapshot consistente pré-instalação: `%APPDATA%\com.cfsjcode.solaris\backups\antes-0.5.8-20261031-213148-4bd61d95\manifest.json`. A verificação pós-instalação aprovou integridade SQLite, contagens de conversas/aprendizado preservadas e Markdown inalterados.
- Aplicativo reaberto; janela e dois processos do engine em execução (um com ~527 MB residentes, compatível com o YOLO26x pré-carregado).
- **Pendente:** a validação visual na janela (refração da topbar/composer na rolagem, barra lateral como lâmina, troca Vidro líquido → Sólido) e a medição de CPU/GPU na rolagem não foram feitas: o acesso de controle à janela foi negado nesta sessão. Não afirmar o efeito visual como validado na janela nativa.

## Atualização 0.5.9 instalada — 01/11/2026

- Conteúdo: tudo o que entrou no main desde a 0.5.8 (main em `4543a64`): #31 (WebGL, luz dinâmica e molas), #33 (memória persistente: instrução prioritária e fallback de extração), #34/#35 (pastas locais e métricas de uso) e #36 (fundo com textura removido). Branch de release `release/0.5.9`.
- Antes do empacotamento: `test:design` (17), `test:annotations` (5), `test:diff` (3) e build do frontend aprovados. Como a release inclui mudanças em Rust e Python, também rodaram 64 testes Python e 20 Rust (`cargo test --lib`), todos aprovados.
- Instalador `Solaris_0.5.9_x64_en-US.msi`: 326.512.640 bytes (311,39 MiB). SHA-256 do MSI: `F8D93A360C2FB12F1A4959DCD6B362538CBAC9C0CF18CD77037669727E3FB754`. Logs em `storage/release-0.5.9/`.
- Snapshot consistente pré-instalação: `%APPDATA%\com.cfsjcode.solaris\backups\antes-0.5.9-20261031-233225-dcb09247\manifest.json`.
- A janela aberta (iniciada às 23:14, ociosa) não atendeu ao pedido de fechamento (WM_CLOSE/taskkill) e foi encerrada à força depois do backup; os processos do engine saíram sozinhos. Windows Installer elevado retornou 0; `solaris.exe` informa 0.5.9. Engine instalado com SHA-256 idêntico ao compilado: `E39D72A037B10CF1DD610C4EDCDE38BFD6A37FE5131E5EC915D33AC76AABCF01`.
- App reaberto: janela e dois processos do engine em execução (um com ~499 MB). A verificação pós-instalação aprovou integridade SQLite, contagens preservadas e Markdown inalterados.
- **Pendente:** a conferência visual (fundo escuro original sem textura, navegação como lâmina de vidro, luz seguindo o ponteiro) e as capturas não foram feitas, porque o acesso de controle à janela foi negado de novo.

## Atualização 0.5.10 instalada — 01/11/2026

- Conteúdo: correção do vinco diagonal no vidro da navegação (#38, main em `181322b`), sobre a 0.5.9. Branch de release `release/0.5.10`.
- Antes do empacotamento: `test:design` (18), `test:annotations` (5), `test:diff` (3) e build do frontend aprovados. Python e Rust não foram reexecutados, porque só o frontend mudou desde a 0.5.9.
- Instalador `Solaris_0.5.10_x64_en-US.msi`: 326.512.640 bytes (311,39 MiB). SHA-256 do MSI: `146D08C9FF75CB58F6428229D2DA36CE539F23C7717FC5C25CC2F0037754F7A3`. Logs em `storage/release-0.5.10/`.
- Snapshot consistente pré-instalação: `%APPDATA%\com.cfsjcode.solaris\backups\antes-0.5.10-20261101-000127-f462e113\manifest.json`.
- Windows Installer elevado retornou 0; `solaris.exe` informa 0.5.10. Engine instalado com SHA-256 idêntico ao compilado: `A5CEEC36AC77A968281B78E2991F9533AFE67DCAFE8480DD97D55A4CC6B8C352`. A verificação pós-instalação aprovou integridade SQLite, contagens preservadas e Markdown inalterados.
- Fechamento: o app não estava aberto antes da instalação, então o teste foi feito depois, na 0.5.10. Aberta há 25 s, a janela fechou com o pedido normal (`CloseMainWindow`) e o engine saiu sem órfãos; o Log de Aplicativos não tem falha do Solaris nas últimas 24 h. A falha de fechamento vista na janela da 0.5.8 não se repetiu, mas o teste não cobre uma janela aberta há muito tempo.
- **Pendente:** a conferência visual da navegação sem a faixa diagonal e as capturas não foram feitas, porque o acesso de controle à janela foi negado. Não afirmar a correção como validada na janela nativa; ela só tem cobertura de `test:design`.

## Atualização 0.5.11 instalada — 01/11/2026

- Conteúdo: gravação de memória tolerante a modelos menores, com parser mais flexível e nova tentativa no pedido explícito de gravação (#40, main em `747c5dc`), sobre a 0.5.10. Branch de release `release/0.5.11`.
- Antes do empacotamento: `test:design` (18), `test:annotations` (5), `test:diff` (3) e build do frontend aprovados. Como a release muda Python e Rust, também rodaram 74 testes Python e 20 Rust (`cargo test --lib`), todos aprovados.
- Instalador `Solaris_0.5.11_x64_en-US.msi`: 326.516.736 bytes (311,39 MiB). SHA-256 do MSI: `4135F48EB6ACDD9A98C884AF4EF1FD4F48DB869CD9879B737FA926B716AAFC22`. Logs em `storage/release-0.5.11/`.
- Snapshot consistente pré-instalação: `%APPDATA%\com.cfsjcode.solarisackupsntes-0.5.11-20261101-160405-b36bbcfc\manifest.json`.
- O app não estava aberto antes da instalação, então não houve fechamento, nem normal nem forçado. Windows Installer elevado retornou 0; `solaris.exe` informa 0.5.11. Engine instalado com SHA-256 idêntico ao compilado: `E02E32E8B26BE7CE13C64AE4AE1FF0ED23795A99EB2E4ACBAB38765002E4DCF0`. A verificação pós-instalação aprovou integridade SQLite, contagens preservadas e Markdown inalterados.
- App reaberto: janela respondendo e dois processos do engine em execução (um com ~446 MB).
- **Pendente:** o teste real de gravação de memória com o Haiku não foi feito, porque o acesso de controle à janela foi negado. A correção só tem cobertura de testes automatizados (`tests/test_memory_small_models.py`), sem chamada a um modelo real. Não afirmar a gravação com o Haiku como validada na janela nativa.

## Referências de compatibilidade

[Documentação oficial YOLO26](https://docs.ultralytics.com/models/yolo26) e [exportação Ultralytics](https://docs.ultralytics.com/modes/export). A compatibilidade desta entrega foi verificada na versão local 8.4.194, com pesos e dependências existentes, sem atualização indiscriminada de bibliotecas.
