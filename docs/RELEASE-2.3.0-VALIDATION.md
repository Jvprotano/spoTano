# spoTano 2.3.0 — Biblioteca

## Entrega

- Categorias combinadas com busca por música/artista e filtro de estado; inclui Não classificada.
- Checkbox por música, cabeçalho com estado parcial e total, Espaço e Ctrl+A.
- Contagem das músicas marcadas; atualização preserva marcações visíveis. Ao filtrar, itens ocultados são desmarcados.
- Editor em massa exige escolha explícita da categoria. Aplica às faixas ou aos artistas principais, com confirmação do escopo ampliado por artista.
- Automática remove a correção; regras individuais mantêm prioridade. Artistas repetidos são processados uma vez.
- Reutiliza reorganização protegida de arquivos e ajustes atuais, sem baixar áudio. Fonte do áudio e MP3 local são individuais.
- Operação em segundo plano, bloqueio durante trabalho e cancelamento entre itens. Em interrupção, ajustes já concluídos permanecem salvos; o lote pode ser aplicado novamente.

## Validação

- 41 testes de interface e classificação aprovados, incluindo filtros combinados, seleção, escopo dos ajustes, Automática, artistas repetidos e reorganização de MP3 sem download.
- Ruff aprovado; git diff --check sem erros.
- Suíte geral: 247 aprovados e um erro de preparação de `tk.PhotoImage` ao carregar o ícone, em 438,14 s. O cenário `test_row_icons_target_clicked_playlist_and_preserve_batch_selection[Detalhes]` passou na repetição isolada (1 aprovado). Um aviso de depreciação veio do spotdl/FastAPI. Não se apresenta essa execução como uma suíte integralmente verde.
- Clique real do Tkinter nas caixas da linha e cabeçalho e acesso aos controles em 1000×760 aprovados. Após o ajuste final do contador, quatro cenários da Biblioteca passaram novamente.
- Executável abriu com catálogo temporário isolado. Smoke do worker congelado aprovado: SDK, FFmpeg, transcodificação de MP3 real e eventos de progresso.
- Auditoria do pacote aprovada: bytecode de nove módulos corresponde ao fonte, CRC do ZIP, EXE igual ao incluído no ZIP, ícones, Python/Tk, licenças, inventário 2.3.0 e ausência de catálogo pessoal. SHA-256 em `dist/SHA256SUMS.txt`.
- Logs e auditoria em `artifacts/library-2.3.0-*`. A primeira tentativa da suíte sem log detalhado foi interrompida por demora e substituída pela execução detalhada acima; os cenários demorados de recuperação de 240 faixas concluíram.
- Captura visual indisponível: Computer Use retornou `native pipe is unavailable`. Interações e geometria são verificadas pelo Tkinter; isso não constitui inspeção visual de glifos e DPI.

## Distribuição local

- Executável: `dist/spoTano/spoTano.exe`.
- ZIP: `dist/spoTano-2.3.0-windows-x64.zip`.
- SHA-256: `dist/SHA256SUMS.txt`.

Extraia a pasta inteira. Python está incluído; o EXE depende dos arquivos ao lado dele. Nenhum catálogo pessoal é necessário para a validação.
