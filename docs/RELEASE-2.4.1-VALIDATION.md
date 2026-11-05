# spoTano 2.4.1 — ações de atualização e retomada

- **Atualizar (Adiciona e Remove)** substitui **Baixar e remover**.
- **Atualizar (Apenas Adiciona novos)** substitui **Baixar / retomar**.
- A prévia e sua confirmação usam a mesma nomenclatura dos botões.
- **Retomar** aparece separadamente quando há downloads registrados como pendentes
  de uma execução iniciada, inclusive após reabrir o aplicativo. Não aparece apenas
  por importar ou consultar playlists. Desaparece ao concluir as pendências.
- A retomada usa a lista salva das playlists pendentes, independentemente das
  playlists marcadas, e mantém a prévia antes de iniciar os downloads.
- Controles ficam desabilitados durante operações. O resumo da seleção e Retomar
  ocupam uma linha acima das três ações permanentes para acomodar os nomes completos.
- Mensagens de cancelamento, exportação e relatórios seguem os novos nomes.

## Validação

Regressões Tk cobrem nomes, operações dos botões, interrupção, reabertura,
retomada sem consulta ao Spotify, preservação da seleção, desaparecimento após
conclusão e limites dos controles na janela mínima de 1000 × 760.

A primeira execução de `tests/test_gui.py` teve 37 aprovações e três falhas na
calibração: a fixture de relatório não incluía o encoder exigido pelo contrato
atual. A fixture foi atualizada, sem alterar o comportamento da calibração.
Os três casos foram repetidos e aprovados: 40 cenários Tk aprovados ao todo.

Também passaram 18 testes de recuperação e auditoria (`test_large_recovery.py`
e `test_download_audit.py`), incluindo interrupção abrupta, reaproveitamento de
arquivos concluídos, tentativas de faixas pendentes e relatórios de falhas.
Ruff e `git diff --check` aprovados.

Inspeção visual por captura indisponível: o serviço Computer Use do Windows
retornou `failed to connect native pipe` em três tentativas, incluindo reinicialização.
A verificação geométrica do Tk não substitui inspeção visual ou validação em outros DPIs.
