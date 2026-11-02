# Redesenho desktop — spoTano 2.0

## Revisão e direção

A interface 1.3.1 repetia instruções, mostrava seis ações de playlist simultâneas,
expunha ferramentas de correção sem seleção e reservava uma área permanente aos
logs. O fluxo principal competia com configuração, manutenção e detalhes técnicos.

A versão 2.0 mantém Tkinter/ttk e os contratos de biblioteca, retomada e exportação.
Usa navegação lateral estável, tipografia Segoe UI, verde reservado à ação principal,
superfícies claras e tabelas com mais espaço para o conteúdo.

## Plano

1. Reestruturar o shell em Playlists, Biblioteca, Exportar e Configurações.
2. Playlists: adicionar por diálogo, seleção explícita, baixar/retomar como ação
   principal; atualização como secundária; substituição, remoção e grupos em Mais ações.
3. Biblioteca: busca, filtro de estado e tabela; abrir correções e fontes de áudio
   somente para uma música selecionada. Manutenção fica em Configurações.
4. Exportar: destino, organização e prévia; indicar que inclui todas as playlists,
   preservar confirmação de cópias e movimentações antes de executar.
5. Configurações: separar downloads, desempenho e manutenção; preservar preferências.
6. Progresso compacto e persistente, cancelamento acessível e logs sob demanda.
7. Conferir estados vazio/preenchido, seleção, diálogos, janela mínima e pacote Windows.
   Sem expansão da suíte unitária; conferência prática isolada, sem alterar dados pessoais.
8. Atualizar versão, documentação, gerar executável, ZIP e SHA-256.

## Limites preservados

Atualizar consulta o Spotify sem baixar/remover áudio. Baixar usa a lista salva;
retomada reutiliza arquivos concluídos. Exportar inclui todas as playlists.
Remoções e substituições continuam com prévia e proteção de arquivos existentes.
Percentuais continuam derivados dos eventos reais. Configurações raras não ocupam
os fluxos cotidianos. A direção visual é exclusivamente desktop Windows.
