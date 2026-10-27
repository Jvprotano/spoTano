# Validação — 26/10/2026

## Otimização 1.1.0

Plano concluído e evidência atual em [OPTIMIZATION-VALIDATION.md](OPTIMIZATION-VALIDATION.md):
129 testes distintos validados, busca de nove faixas reais em 0,344–2,078 s,
lotes sintéticos de 200 faixas com 2/3/4 executores e executável Windows com
200 amostras geradas, 200 perfis/hashes conferidos e zero falhas. Os testes
sintéticos não estimam a duração de downloads reais do YouTube.

O histórico abaixo corresponde às etapas anteriores desta implementação.

## Primeiro download, barra verde e acesso aos arquivos

- 94 testes locais passaram no Windows, sem testes pulados. Ruff, formatação e
  `git diff --check` conferidos. A suíte inclui nove testes da interface Tk.
- Ação principal `Baixar tudo`, inclusive na confirmação e na orientação após
  importar. Mantém o download de todas as faixas da lista salva e a preservação
  dos arquivos anteriores até validar os novos.
- `Atualizar selecionadas` só fica disponível para seleções com download anterior
  concluído. Se todas as marcadas já têm algum áudio local ou download concluído,
  mas há uma playlist parcial, a ação é `Continuar download`, com reutilização.
  Uma seleção que inclui playlist sem áudio local nem download concluído mantém
  a atualização desativada. Estados e retomada verificados com download simulado,
  falha parcial e persistência no catálogo temporário.
- Barra verde conferida pelo estilo Tk e visualmente em 1000 × 760; ação principal,
  segunda linha da lista e botão de exportação permanecem acessíveis.
- `Abrir pasta dos downloads` no painel é um atalho para a biblioteca compartilhada.
  Resultados de download e exportação mostram o caminho e oferecem `Abrir pasta`.
  Testes conferem que o download usa `Music` e a exportação usa seu destino real.
  Nenhum catálogo do usuário foi modificado pela validação.

## Contador do lote e processos sem terminal

- 91 testes locais passando no Windows, sem testes pulados; Ruff e formatação
  conferidos. A suíte inclui interface Tk em 1000 × 760 e conversão real de
  áudio sintético, além de falha parcial, reutilização e cancelamento.
- Inspeção visual de janela descartável em 1000 × 760: resumo em destaque,
  logs com bytes e percentual de conversão, barra e ações visíveis. As contagens
  dessa prévia eram simuladas e o catálogo do usuário não foi aberto.
- Executável Windows reconstruído e verificado por `smoke_frozen.py` e
  `smoke_download_sessions.py`: conversão local, dois áudios próprios servidos
  em loopback, um só mecanismo reutilizado, eventos de transferência e 100% de
  conversão recebidos, MP3/ID3v2.3 conferidos. Nenhuma playlist externa foi
  baixada para essa validação; não foi feito benchmark comparando 2 e 3 downloads.
- Barra determinada pelo total de faixas processadas, com resumo persistente de
  concluídas, baixadas, falhas e reutilizadas. Progresso de outra faixa não apaga
  o resumo; cancelar preserva a posição e a contagem. Nova operação reinicia o
  indicador. Falhas avançam a fila sem serem contadas como downloads salvos.
- Hooks reais do spotDL capturam os bytes originais do yt-dlp e o percentual do
  FFmpeg antes de a interface simples do SDK descartar esses valores. Total
  desconhecido permanece desconhecido; estimativas são identificadas com `~`.
  Busca e leitura de metadados continuam sem percentual. Eventos são limitados
  a um por segundo por etapa, preservando mudanças de etapa e conclusão.
- Política restrita ao worker: `CREATE_NO_WINDOW` em processos do SDK, inclusive
  subclasses já carregadas pelo asyncio. Teste Windows executa filhos reais
  síncronos e assíncronos, confere ausência de console, preservação das flags
  anteriores e restauração do construtor ao sair do contexto.
- Logs enviados pelo usuário: de 15:46:38 a 15:51:07, quatro eventos `Salvo` e
  três outras faixas iniciadas; encerramento do cancelamento às 15:51:10. A faixa
  Rosas, Versos e Vinhos permaneceu buscando correspondência por mais de quatro
  minutos. Conversões concluídas levaram aproximadamente 19 a 50 segundos.
  Não há evidência nesses logs para atribuir a demora ao paralelismo nem para
  afirmar que seis ou sete arquivos terminaram de baixar.

## Downloads reutilizáveis, paralelismo e gêneros

- 87 testes locais passando. Consulta de playlist e atualização de dados continuam
  explícitas; baixar novamente usa o snapshot salvo e mantém a data da leitura.
- Fila com até dois downloads por padrão, configurável de um a quatro. Testes
  verificam execução simultânea limitada, cancelamento sem iniciar o restante
  da fila, arquivos anteriores preservados e processos encerrados ao terminar.
- Protocolo entre processos exercitado com subprocessos reais: duas faixas usam
  um mecanismo só; timeout mata o processo e a próxima faixa cria outro;
  cancelamento encerra o processo ativo. Cada executor tem temporários próprios.
- O teste com SDK spotDL e FFmpeg reais converteu dois áudios sintéticos com o
  mesmo Downloader/event loop e bloqueou qualquer chamada de rede ou ao Spotify.
  A medição de 0,73 s cobre apenas amostras de 1 segundo e não representa o tempo
  de músicas completas nem buscas/downloads externos.
- A concorrência revelou uma particularidade de `Path.resolve` no Windows:
  criação simultânea de uma pasta pode manter o prefixo `\\?\` em apenas um
  dos caminhos. Comparação normalizada corrigida, preservando a rejeição de
  escapes e a resolução de links/junctions, com regressão específica.
- Consultas reais de gênero: Hugo & Guilherme sem tags no MusicBrainz e com
  Sertanejo no Wikidata; Gusttavo Lima com Sertanejo no MusicBrainz. O catálogo
  de teste é separado do catálogo do usuário. Corrigir Outros pode reutilizar
  áudio já salvo e nunca sobrepõe correções manuais.
- Resultados vazios legados não prendem uma classificação por 90 dias.
  Gêneros reconhecidos: 90 dias; ausência confirmada: 1 dia; falhas de rede:
  apenas no lote atual, com diagnóstico visível. O caso real também exercitou
  HTTP 503 do MusicBrainz e a fonte alternativa.
- Não foi feito benchmark de uma playlist de 200 músicas nem comparação de
  velocidade de downloads externos. Os ganhos estruturais foram verificados;
  os tempos dos provedores continuam variáveis.

## Atualização de UX: seleção, pastas e progresso

- 70 testes locais passando, sem testes pulados. Incluem importação sem áudio,
  falha sem cadastro parcial, seleção normal/forçada, playlists não selecionadas
  preservadas, comparação persistida após falhas e avanço independente por playlist.
- Exportação nos modos unificado, por playlist e por grupo, com leitura dos bytes
  copiados, deduplicação por grupo, colisões de nomes ASCII/case, reutilização,
  mudança de organização com lixeira e rejeição de prévias antigas.
- Migração de catálogo antigo reaberto sem repetir a migração; a prévia identifica
  que a referência legada é a última lista salva, sem inventar conclusão de download.
- Eventos estruturados do worker entregues enquanto o processo ainda está ativo;
  espera sem eventos, timeout e cancelamento verificados. Callback do spotDL
  exercitado para transferência e conversão. Integração com FFmpeg real e áudio
  sintético continuou passando, incluindo log da conversão no processo isolado.
- Cinco testes Tk com uma única sessão de interpretador, cobrindo checkboxes,
  bloqueio de controles, prévia selecionada, fila de logs, grupos e remoção.
  A janela em 1000 × 760 também mantém as linhas das playlists e o botão de
  exportação acessíveis, com logs ampliáveis e configuração de saída com rolagem.
  Criar/destruir vários interpretadores Tk nesta instalação falhava ao localizar
  tk.tcl; usar uma sessão com janelas de teste separadas resolveu a limitação.
- Janela Windows inspecionada: ações desativadas sem marcação, liberação após marcar,
  prévia limitada à marcada e logs avançando durante simulação de download com
  dados descartáveis. Essa simulação visual não é evidência de download externo.
- Consulta real via worker: Today’s Top Hits, nome e 50/50 faixas importados,
  nenhum áudio baixado. Eventos de espera e leitura recebidos durante a consulta.
- A organização escolhida se aplica à coleção exportada (pasta local ou pendrive);
  a biblioteca interna continua mantendo uma cópia por faixa. A exportação inclui
  todas as playlists importadas, conforme informado na interface.

## Validação original da versão 1.0.0

Evidências confirmadas nesta máquina Windows x64 com Python 3.12.3:

- 46 testes passando em CI Windows e Linux: referências compartilhadas, reinício, incremental, falhas
  parciais, download forçado com preservação, MP3 inválido, prévia obsoleta,
  correções, organização por artista, lixeira, cancelamento, backup SQLite,
  proteção de caminhos e manifesto, exportação incremental e conflitos.
- Teste de integração com áudio gerado localmente: FFmpeg real → worker isolado
  → validação MP3 → SQLite reaberto → exportação → segunda exportação sem cópias.
- Consulta real à playlist pública Today’s Top Hits: 50 faixas, total conferido.
  Somente metadados consultados; nenhuma música dessa playlist foi baixada.
- Consulta real à playlist pública All Out 80s: 150 de 150 faixas, sem itens
  ignorados, confirmando leitura de playlist maior que uma página.
- Download real de teste com a faixa **Carefree**, Kevin MacLeod, disponível
  sob [CC BY 4.0](https://incompetech.com/music/royalty-free/index.html?gt=&isrc=USUAN1400037).
  Créditos: "Carefree" Kevin MacLeod (incompetech.com), CC BY 4.0.
  O teste detectou e motivou correção do tratamento de caminho de saída upstream.
  Repetição com o adaptador corrigido e Deno instalado: arquivo de 4.963.624 bytes
  recebido no caminho solicitado e validado como MP3 44,1 kHz estéreo.
  Nenhum áudio é incluído no repositório ou nas releases.
- Ruff check e formatação executados no código e testes.
- Janela desktop aberta e inspecionada visualmente no Windows.
- Cadastro de playlist e prévia real de 50 downloads validados pela interface;
  prévia cancelada, sem baixar a playlist de terceiros.
- Detecção de componentes: FFmpeg e Deno preparados com sucesso pelo worker.
- Consulta real ao MusicBrainz: Metallica classificada como Rock e Metal após
  filtrar votos negativos e corrigir limites de palavras. Teste de áudio confirmou
  192.000 bps, 44.100 Hz, dois canais e ID3v2.3.
- Detecção USB executada no Windows: nenhum dispositivo conectado no momento;
  não equivale a teste em um pendrive físico.

A validação de hardware (pendrive físico e rádio Cerato 2011) não foi feita.
Serviços externos podem mudar, limitar consultas ou recusar áudio. Testes locais
não certificam download universal, matching perfeito ou disponibilidade futura.

O [pipeline](https://github.com/Jvprotano/spoTano/actions) exige testes em Windows
e Linux antes da release. Em tags, também executa `scripts/smoke_frozen.py` sobre
o EXE gerado: importa SDKs dentro do pacote, converte áudio local com FFmpeg e
confere o MP3. Só então publica ZIP, fontes correspondentes e checksums.
Esse teste é independente dos testes Python da biblioteca.

## Release publicada e conferida

[v1.0.0](https://github.com/Jvprotano/spoTano/releases/tag/v1.0.0) publicada pelo
[workflow 40330606186](https://github.com/Jvprotano/spoTano/actions/runs/40330606186),
com 46 testes passando em cada plataforma e smoke do EXE passando.
O ZIP publicado foi baixado novamente nesta máquina: hash SHA-256 conferido,
ausência de áudios/catálogos/arquivos .env verificada e smoke do worker repetido
com sucesso. A janela do executável publicado também abriu e foi inspecionada.

ZIP Windows: 54.076.730 bytes. SHA-256:
`97d966185e94ab4fe2ae6dee1adc4aaf5adda112c9d3d24c79e80407a5c33a7a`.

A primeira tentativa de envio da release falhou por diferença de maiúsculas no
nome dos assets. O workflow em main foi corrigido; a publicação foi repetida
com a mesma tag verificada, sem reescrever seu histórico.
