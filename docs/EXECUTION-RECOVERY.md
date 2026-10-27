# Biblioteca e retomada de playlists grandes

## Comportamento

- A Biblioteca contém as faixas desde a importação da playlist, antes de baixar áudio.
- Aplicar à faixa salva uma correção individual. Aplicar ao artista salva uma regra
  para o artista principal, inclusive para faixas futuras; a correção individual tem prioridade.
- Correções reorganizam os MP3s disponíveis imediatamente quando Categoria está
  habilitada. As tags acompanham a correção quando Metadados está habilitado.
  Não há outro download de áudio. Outras faixas não são reorganizadas por uma correção individual.
- Exportações existentes no computador ou pendrive são atualizadas ao exportar novamente.
- Baixar / retomar fica disponível sempre que há playlists marcadas, inclusive
  imediatamente após importar e após reabrir o aplicativo.

## Persistência e interrupções

`download_pending` registra a fila confirmada por playlist e faixa antes de começar
a operação. Só a instalação de áudio concluído retira a pendência; reorganizar
pastas ou alterar tags não conclui uma substituição de áudio pendente.

A conclusão da faixa e a retirada da pendência são gravadas na mesma transação.
O journal `file_transitions` permite reconciliar uma interrupção entre a troca do
arquivo e o registro no catálogo. Um MP3 antigo válido permanece utilizável se a
substituição falhar, mas não esconde a substituição pendente na retomada.

As playlists com pendências ficam marcadas ao reabrir o aplicativo. A retomada usa
a lista salva, sem exigir outra consulta ao Spotify. Baixar tudo continua sendo uma
solicitação explícita para refazer todos os áudios; para continuar um lote parcial,
use Baixar / retomar. Faixas compartilhadas são baixadas uma vez.

A recuperação é por faixa concluída, não por byte da transferência interrompida.
Arquivos alterados externamente continuam protegidos para revisão. Uma atualização
completa do Spotify remove da fila apenas pendências que saíram daquela playlist.
O histórico do último download completo continua separado da fila parcial.

## Validação reproduzível

`tests/test_large_recovery.py` usa 240 faixas, SQLite e arquivos reais em diretórios
temporários, com provedor e conteúdo de áudio sintéticos:

- Falhas de conexão em 15 faixas, com quatro downloads paralelos, e retomada das
  pendências após reabrir com a consulta ao Spotify indisponível.
- Detecção de arquivo ausente e preservação de arquivo alterado externamente.
- Cancelamento após pelo menos 73 arquivos salvos, com quatro downloads paralelos.
- Encerramento abrupto do processo por `os._exit`, após 73 arquivos salvos:
  primeiro download e substituição forçada de uma coleção já baixada.
- Preservação dos hashes dos arquivos concluídos ao retomar os 167 restantes.
- Interrupção após trocar o arquivo, antes de concluir seu registro, e recuperação
  do journal junto com a fila.
- Retagging e outra playlist não descartam uma substituição pendente.

`tests/test_library_classification.py` cobre classificação antes do download,
regras para futuras faixas, prioridade individual, movimentação imediata e tags.
`tests/test_gui.py` cobre acesso à retomada, seleção após reiniciar e tamanho mínimo.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check spotano tests scripts/smoke_recovery_ui.py
.venv\Scripts\python.exe -m scripts.smoke_recovery_ui
```

A demonstração visual usa um catálogo temporário separado. As abas Playlists e
Biblioteca foram inspecionadas no Windows em 1000 × 760; os controles ficam acessíveis.
Esses testes não equivalem a baixar uma playlist real de 240 músicas pela internet,
nem estabelecem um prazo ou garantem disponibilidade de gravações no provedor.
