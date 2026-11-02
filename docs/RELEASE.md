spoTano 2.3.1 corrige a identificação de participações entre colchetes, evita reavaliar candidatos idênticos e limpa diagnósticos entre faixas.

Pacote: `dist/spoTano-2.3.1-windows-x64.zip`. Consulte [análise e validação](RELEASE-2.3.1-VALIDATION.md).

spoTano 2.3.0 adiciona filtros por categoria e ajustes em massa na Biblioteca.

- Filtro por categoria, incluindo Não classificada, combinado à busca e ao estado.
- Checkboxes por música e no cabeçalho; Espaço marca a linha e Ctrl+A alterna as visíveis.
- Ajustar marcadas aplica categoria às faixas ou aos artistas principais, com confirmação do escopo por artista. Automática remove a correção manual.
- Seleção limitada à lista visível: músicas ocultadas pelos filtros são desmarcadas. Nenhuma categoria vem pré-selecionada no editor em massa.
- Mesmas regras de reorganização dos arquivos locais, sem baixar áudio. Exporte novamente para atualizar o pendrive.

Pacote portátil: dist/spoTano-2.3.0-windows-x64.zip. Validação: docs/RELEASE-2.3.0-VALIDATION.md.

A versão inclui as melhorias de playlists da 2.2.0:

- Sem o botão Mais ações: atualizar do Spotify, detalhes, pasta/grupo e remover ficam como ícones em cada linha. As ações afetam somente aquela playlist, independentemente das caixas marcadas.
- Baixar / retomar, Baixar tudo e Baixar e remover sempre visíveis. São habilitados ao marcar uma ou mais playlists e bloqueados durante uma operação.
- Uma caixa no cabeçalho marca ou desmarca todas. O indicador intermediário mostra uma seleção parcial.
- Removidos os botões Marcar todas, Desmarcar e o atalho Personalizar da tela de playlists. Preferências permanecem em Configurações → Downloads.
- Ícones com dicas e atalhos: F5 para atualizar, Enter para detalhes, Ctrl+G para pasta/grupo e Delete para remover a linha em foco. Espaço marca a linha; Ctrl+A alterna todas.
- Prévias e confirmações preservadas. Remover playlist mantém os arquivos locais; Baixar e remover mantém as proteções para faixas compartilhadas e downloads com falhas.

Pacote portátil local: dist/spoTano-2.2.0-windows-x64.zip. Extraia a pasta inteira e abra spoTano.exe. O executável precisa dos arquivos que acompanham a pasta; Python já está incluído.

Conferência desta entrega: docs/RELEASE-2.2.0-VALIDATION.md.

A versão mantém os testes rápido e completo para escolher o paralelismo:

- **Teste rápido** em destaque: quatro músicas, duas rodadas e perfis 1/1, 2/2, 3/3 e 4/4. Inclui a configuração atual quando diferente: 8–10 lotes, 32–40 downloads.
- **Teste completo**: todas as 16 combinações, três rodadas e amostra de quatro ou oito músicas: 48 lotes, 192 ou 384 downloads.
- Playlist de teste padrão, alterável nas configurações, sem exigir playlists importadas.
- Ranking por mediana, músicas/minuto, variação, falhas e indicação da configuração inicial. O rápido fornece uma recomendação inicial entre os perfis testados.
- **Aplicar configuração recomendada** salva os dois valores juntos. Resultados parciais, com falhas, instáveis ou de opções desatualizadas não permitem recomendação aplicável.
- Relatórios, métricas e cronograma preservados para revisão. Biblioteca pessoal, fontes manuais e caches originais são mantidos.

O tempo depende da máquina, rede e provedor. O ensaio do modo rápido com áudio gerado e SDK/FFmpeg reais concluiu oito lotes em 3min05s; não é previsão de tempo para o YouTube. Método e limites: docs/PERFORMANCE-CALIBRATION.md.

A versão inclui a identidade visual introduzida na 2.0.1:

- Novo ícone em verde e marfim: uma nota musical com seta representa levar sua música com você.
- Ícone incluído no executável, nos atalhos criados para ele e nas janelas do aplicativo, com múltiplas resoluções para o Windows.
- Identidade própria na barra de tarefas, inclusive ao executar pelo Python.
- Recursos visuais incluídos no pacote portátil e nas instalações Python.

A experiência desktop mantém:

- Navegação lateral com Playlists, Biblioteca, Exportar e Configurações.
- Playlists com adicionar por diálogo, downloads visíveis no rodapé e ações individuais na lista.
- Biblioteca com busca e filtros por estado. Detalhes e ajustes reúne categoria, fonte do áudio e MP3 local, com seleção explícita.
- Exportação com destino, organização e prévia; confirmação antes de copiar ou movimentar arquivos.
- Configurações divididas em Downloads, Desempenho, Manutenção e Sobre.
- Atividade recolhível com logs, contagens reais, cancelamento e acesso à pasta dos downloads.
- Estados vazios, atalhos de teclado e organização do código visual em módulos próprios.

Mantém os dados existentes, opções de download, retomada persistente e proteção dos arquivos. Não altera os contratos de consulta, download ou exportação.

Baixe o ZIP Windows, extraia a pasta inteira e abra spoTano.exe. O executável depende dos arquivos que acompanham a pasta; Python já está incluído. No primeiro uso, prepare FFmpeg e Deno em Configurações → Downloads.

Conferência da 2.1.0: docs/RELEASE-2.1.0-VALIDATION.md. Evidências anteriores da identidade e interface em docs/ICON-VALIDATION.md e docs/ui-redesign/VALIDATION.md. Downloads com provedor, pendrive e rádio físico ficam para validação de uso.
