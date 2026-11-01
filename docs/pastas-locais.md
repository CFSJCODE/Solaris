# Pastas locais vinculadas ao projeto

Implementado em 01/11/2026 (PR "Pastas locais"). Ainda **não empacotado nem instalado**; validar no Windows antes de afirmar uso real.

## O que faz

| Função           | Como funciona                                                                                                                                                                                                                                                                                                                                                           |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anexar pasta     | Aba **Pastas locais** do projeto → seletor nativo (`tauri-plugin-dialog`). Até 8 pastas por projeto; a raiz de uma unidade é recusada.                                                                                                                                                                                                                                  |
| Persistência     | Tabela `project_folders` no `solaris.db`. O vínculo sobrevive a reinícios; desvincular apaga só o índice, nunca arquivos da pasta.                                                                                                                                                                                                                                      |
| Indexação        | Rust percorre a pasta sem seguir links simbólicos, ignora `.git`, `node_modules`, `target`, `build`, `.pio`, `.venv` etc. Texto/código até 2 MB lido direto; PDF/DOCX até 10 MB extraídos pelo engine (`extract_text`). Incremental por tamanho+mtime. Máximo de 4.000 arquivos por pasta.                                                                              |
| Segredos         | `.env*` (exceto `.example/.sample/.template`), `*.pem`, `*.key`, `id_rsa*`, nomes com `secret`/`credential`, `.npmrc`, `.netrc` nunca são indexados, lidos nem editados.                                                                                                                                                                                                |
| Contexto no chat | (1) Resumo das pastas e até 200 caminhos no prompt de sistema; (2) busca FTS5 nos trechos (`folder_fts`) quando "Buscar no projeto" está ativo, até 10 mil caracteres; (3) arquivos citados com `@caminho` (ou `@"caminho com espaço"`) entram inteiros, até 24 mil caracteres no total. Fontes aparecem como "Pasta local".                                            |
| Navegação        | Filtro por caminho, pré-visualização do conteúdo atual e botão **Citar no chat**. No chat, o menu **Pastas locais** insere a menção no texto.                                                                                                                                                                                                                           |
| Edição           | O modelo responde com `<solaris_edit pasta="ID" caminho="rel/arq">conteúdo completo</solaris_edit>`. O Rust remove o bloco da mensagem, registra uma proposta pendente (`folder_edits`) e a UI mostra o diff por linhas.                                                                                                                                                |
| Aprovação        | Só o clique **Aprovar e gravar** grava. Antes: confere se o arquivo mudou no disco desde a proposta (senão `conflict`), copia a versão anterior para `storage/folder-backups/edit-<id>/` e grava via arquivo temporário + rename. Mantém CRLF do original. `.git`, dependências, segredos e executáveis/scripts do Windows (`.exe`, `.bat`, `.ps1`…) não são graváveis. |

## Limites conhecidos

- Busca é lexical (FTS5), não semântica; mesma decisão do restante do RAG local.
- O modelo não lista diretórios nem executa comandos sozinho: só vê o que o contexto entrega. Para arquivos fora dos trechos recuperados, o usuário cita com `@caminho`.
- Edições substituem o arquivo inteiro; arquivos acima de 1 MB não recebem propostas.
- Não há observador de sistema de arquivos; use **Atualizar índice** após mudanças externas (edições aprovadas reindexam o próprio arquivo).

## Arquivos

- `src-tauri/src/workspace.rs` — núcleo sem Tauri: varredura, `safe_join`, extração de propostas, SQLite, gravação com conflito/backup. Testes unitários.
- `src-tauri/src/folder_commands.rs` — comandos IPC `folder_*`.
- `src-tauri/src/commands.rs` — integração em `chat_send` e evento `edit_proposals`.
- `frontend/src/components/FolderPanel.tsx`, `EditProposals.tsx`, `lineDiff.ts`.
- Testes: `cargo test` (workspace::tests), `npm run test` de `tests/lineDiff.test.mjs`, `tests/ui/folders.spec.ts` (Playwright com IPC simulado).
