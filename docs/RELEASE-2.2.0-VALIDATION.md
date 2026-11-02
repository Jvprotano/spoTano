# Conferência do pacote Windows 2.2.0

Entrega local de 02/11/2026 com simplificação da tela de playlists. Usa o checkout
atual, preservando alterações anteriores; sem publicação no GitHub.

## Interface

- Ações na linha: atualizar, detalhes, pasta/grupo e remover. Cada ação usa o ID
  daquela linha e preserva a seleção das caixas para os downloads em lote.
- Caixa geral no cabeçalho, com estados vazio, parcial e completo. Cliques
  consecutivos alternam a seleção; Ctrl+A e Espaço também são suportados.
- Três downloads sempre visíveis, desabilitados sem marcação ou durante uma
  operação. As prévias e proteções de arquivos mantêm o comportamento anterior.
- Removidos Mais ações, Marcar todas, Desmarcar e o atalho Personalizar.
- Dicas nos ícones e atalhos F5, Enter, Ctrl+G e Delete. Nome completo disponível
  na dica da playlist e nos detalhes.

## Verificação

- Ruff passou em spotano, scripts e tests.
- 34 cenários de interface exercitados. A execução final aprovou 33; um cenário
  teve erro transitório na preparação de `tk.PhotoImage` ao carregar o PNG do ícone
  e passou na repetição isolada (1 aprovado). Logs `gui-final.log` e `gui-retry.log`
  em `artifacts/release-2.2.0/`. Incluem seleção vazia,
  parcial e total, cliques nos ícones, escopo individual, cancelamento da remoção,
  bloqueio durante trabalho, retomada e layout mínimo de 1000×760.
- Testes antigos foram adequados aos controles atuais, incluindo configurações,
  editor de faixa e atividade recolhível.
- 35 testes adicionais de ações de playlist, sessões de download, recuperação e
  opções aprovados. Um aviso de depreciação do FastAPI veio da dependência spotdl.
- Smoke do executável aprovado: imports do SDK, FFmpeg, transcodificação real
  de MP3 local gerado e eventos de progresso.
- Smoke de sessão aprovado com duas amostras próprias em loopback: um processo
  reutilizado, MP3 validado, progresso de transferência/conversão e encerramento
  do worker, em 51,47 segundos. Não mede a velocidade do provedor real.
- Executável abriu com catálogo novo e isolado, título correto e janela
  responsiva. A instância de conferência foi encerrada após a verificação.
- Conferência visual por captura indisponível: o serviço Computer Use do Windows
  retornou `native pipe is unavailable` em tentativas e após reinicialização.
  Dimensões, visibilidade e eventos foram conferidos diretamente pelo Tkinter;
  isso não substitui revisão visual dos glifos e escalas de texto/DPI.

## Distribuição

Pacote: `dist/spoTano-2.2.0-windows-x64.zip`.
Executável: `dist/spoTano/spoTano.exe`.
Checksum: `dist/SHA256SUMS.txt`.

Extraia a pasta inteira do ZIP. O EXE depende dos arquivos que o acompanham;
Python está incluído. Dados pessoais ficam fora do pacote.

Auditoria em `artifacts/release-2.2.0/package-audit.json`: executável x64,
bytecode dos módulos da aplicação correspondente ao fonte atual, CRC do ZIP,
executável do ZIP igual ao da pasta, recursos de Python/Tk, ícones, licenças,
documentação, inventário `spotano==2.2.0`, ausência de catálogo pessoal e SHA-256.

Logs de testes, build, smoke e auditoria são mantidos em `artifacts/` e `dist/`
no checkout. Não representam teste de disponibilidade do provedor real,
calibração de throughput, pendrive ou rádio físico.
