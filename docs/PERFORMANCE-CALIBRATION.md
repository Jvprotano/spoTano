# Revisão do teste de configuração recomendada — 30/10/2026

O teste anterior não cobria o espaço dos controles: começava em 1/1, 2/2, 3/2 e
4/2, escolhendo depois conversões somente no melhor nível de downloads. Uma
interação favorável em outra combinação podia ficar de fora. Duas rodadas e média
sem verificação de variação também permitiam uma recomendação dominada por ruído.
A apresentação seguia a ordem de execução e não permitia comparar configurações
agregadas de imediato. O início dependia de playlists importadas e marcadas.

## Método implementado

- Dois modos: **rápido** como ação principal e **completo** como opção de maior
  cobertura. O rápido usa quatro músicas, duas rodadas e os perfis 1/1, 2/2, 3/3,
  4/4, acrescentando a configuração atual quando assimétrica. São 8–10 lotes e
  32–40 downloads. Incluir a configuração atual evita recomendar uma troca sem
  medi-la junto dos candidatos. O modo é registrado no relatório e no resultado.
- No completo, produto cartesiano dos controles: downloads 1–4 × conversões 1–4.
  São 16 combinações e três rodadas completas, totalizando 48 lotes.
  O pipeline tem um áudio por processo de download; conversões acima desse número
  não ampliam a concorrência efetiva. Mesmo essas combinações são medidas, para
  cobrir todos os valores que o usuário pode selecionar nos controles.
- Playlist pública padrão `0aoPyrSGmKxpwxzN9NDr7c`, alterável em Configurações.
  A consulta não importa playlists/faixas na biblioteca pessoal. A amostra de 4 ou
  8 músicas deduplica IDs e seleciona quantis de duração, incluindo os extremos.
  Isso melhora a diversidade de duração, mas não representa necessariamente todos
  os artistas, gravações, gêneros ou condições de busca de uma coleção.
- Mesma amostra em todos os lotes. Ordem inicial das configurações sorteada;
  segunda rodada em ordem inversa; no completo, terceira novamente sorteada. A ordem das
  músicas é sorteada por rodada, igual para todas as configurações nessa rodada.
  Semente e cronograma ficam registrados para auditoria.
- Cada medição passa por `Library.apply`, incluindo preparação dos processos,
  busca, transferência, classificação e conversão conforme as opções habilitadas.
  Catálogo/caches/áudios locais novos em cada lote. Preparação do catálogo isolado
  e cópia dos diagnósticos ficam fora do cronômetro.
- Opções, fontes opcionais e organização de saída são fixadas no início. Fontes
  manuais e correções são copiadas para o ambiente temporário. Credenciais não
  são persistidas nos relatórios. O catálogo e os caches originais são preservados.
- Ranking crescente pela mediana dos lotes completos sem falhas (dois no rápido,
  três no completo). O relatório
  mantém média, mínimo, máximo, músicas/minuto, falhas e tempos por fase. Medições
  com tempo inválido, amostras diferentes, falhas ou rodadas ausentes/repetidas
  não recebem classificação.
- Variação observada = `(máximo − mínimo) / mediana`. Acima de 15% no rápido ou
  25% no completo, a configuração
  aparece como instável. É um limiar operacional conservador, não um intervalo de
  confiança nem prova de significância. O rápido usa um limite mais estrito por
  ter menos observações. Nenhum desses números certifica desempenho.
- Entre configurações estáveis até 5% da menor mediana observada, prefere menos
  processos. Se nenhuma das mais rápidas nessa margem for estável, não recomenda
  uma opção muito mais lenta só por ela ter sido estável. O ranking continua por
  velocidade, mesmo quando a recomendação fica em outra posição dentro da margem.
- A aplicação exige terminar todas as medições previstas no modo escolhido.
  Cancelamentos/falhas salvam resultados parciais. Relatórios v2 do completo
  continuam aplicáveis porque usam o mesmo protocolo; o antigo método por etapas
  pede novo teste. A aplicação recalcula a recomendação a partir das medições, confere as
  opções atuais e grava os dois controles na mesma transação SQLite.

## Apresentação

Antes de começar, a prévia informa playlist, quantidade de lotes/downloads,
consumo e possibilidade de cancelamento. A execução acontece em segundo plano,
com contador de lote e rodada. A conclusão apresenta tabela ordenada, mediana,
músicas/minuto, variação, estado e destaque da configuração recomendada.
O botão **Aplicar configuração recomendada** fica disponível somente para um
resultado aplicável. O usuário também pode abrir a pasta de evidências ou as
medições individuais. Após aplicar, ambos os controles e a mensagem de estado
confirmam os valores salvos. A tabela marca como **Inicial** a configuração que
estava em uso antes do teste, para facilitar a decisão de mantê-la ou trocar.

## Limites e fundamentação

A recomendação rápida é inicial e vale somente para os perfis medidos. Não há
inferência de resultados para combinações não testadas, nem uso de um único lote
para escolher uma configuração. Pode deixar de encontrar uma combinação
assimétrica melhor; o completo é a opção para explorar esse espaço. Em relação
ao completo padrão (8 músicas), reduz 79–83% dos lotes e 90–92% dos downloads.
Esses percentuais são redução de trabalho, não promessa de redução igual do tempo.

A medição responde qual configuração funcionou melhor nessa amostra, nessas
opções e condições. Não elimina caches do sistema operacional/CDN/provedor,
limites remotos, variações da rede, aquecimento do computador ou outros programas.
Não mede separadamente o cenário de uma biblioteca/cache já aquecidos. Amostras
curtas dão peso maior à preparação que uma playlist de centenas de faixas.
Uma recomendação real requer executar o teste na máquina do usuário; o ensaio
com áudio gerado valida o pipeline, sem prever o desempenho do YouTube.

O sorteio e a organização em rodadas seguem o princípio de reduzir efeitos de
variáveis externas descrito pelo [NIST, Randomized block designs](https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm).
A exposição de dispersão e rejeição de recomendações instáveis também é coerente
com a orientação do [pyperf para analisar resultados instáveis](https://pyperf.readthedocs.io/en/latest/analyze.html).
Os limiares de 15%, 25% e 5% são políticas do aplicativo; não vêm dessas referências.

## Validação dos modos rápido e completo

- **26 testes focados passaram** (`26 passed, 18 deselected`). Uma execução anterior
  teve um erro transitório de `PhotoImage` na montagem da janela; os seis testes
  de desempenho da interface passaram isoladamente e a repetição conjunta terminou
  sem erros. Não houve alteração no módulo de ícones.
- Ensaios controlados conferem os oito lotes do rápido, dez quando a configuração
  atual é assimétrica, inclusão de 3/1, ordem inversa, amostra fixa de quatro músicas,
  preservação dos controles, serialização/reabertura e bloqueio de resultados
  incompletos. O teste completo continua cobrindo todas as 48 medições.
- O limite mais estrito de variação do rápido foi exercitado com medições aceitas
  pelo completo e rejeitadas pelo rápido. A interface identifica o modo e a
  recomendação inicial, distingue a configuração em uso no início e mantém a
  aplicação explícita dos dois valores. Relatórios v2 do completo continuam válidos.
- Ensaio real do modo rápido com SDK/FFmpeg, áudio de um segundo gerado e servido
  em loopback: **8 lotes, 32 downloads/conversões, zero falhas, 185 segundos**.
  Dados em `artifacts/performance-review/quick-sdk.json`. O script também confere
  remoção dos áudios/catalogos temporários de cada lote e preservação da biblioteca
  original e seus controles. A duração é desse ensaio local, sem previsão para o
  YouTube. Duas configurações foram marcadas instáveis, exercitando a restrição de
  recomendação. A recomendação gerada pelo ensaio não foi aplicada ao catálogo pessoal.
- Ruff, formatação e diff conferidos. Não foi repetida a suíte geral, cuja limitação
  de interface está registrada abaixo. Não foi recriado o executável nem refeita a
  inspeção visual por screenshot nesta etapa; a interação foi verificada com Tk.

## Validação anterior, antes da inclusão dos modos

- `20 passed, 18 deselected`: testes focados de política, cobertura 16×3, interação
  que escapava da busca por etapas, tempos inválidos, rodadas duplicadas, amostras
  diferentes, falhas, cancelamento, preservação de fontes/correções/cache,
  resultado antigo, opções desatualizadas, biblioteca vazia e aplicação explícita.
  O teste de isolamento também confere a preservação byte a byte do catálogo original.
- Suíte fora da interface: **194 passed, 1 warning**, em 537,37 segundos. O aviso
  vem da API web opcional do spotDL sobre o evento de encerramento do FastAPI.
  Os 16 casos de benchmark fazem parte dessa suíte e também da execução focada;
  não se somaram as duas contagens como testes distintos.
- Consulta real ao Spotify confirmou a playlist **Teste spotTano**, com 11 faixas;
  seleção de oito IDs distintos validada. Nenhuma playlist foi importada no catálogo
  pessoal durante essa conferência.
- Ensaio adicional com SDK/FFmpeg reais e áudio de um segundo gerado/servido em
  loopback: 12 lotes concluídos, 48 downloads/conversões sem falhas. Foi encerrado
  antes das 48 medições, após o custo observado subir para cerca de um minuto por
  lote. Essa evidência é parcial e não produz recomendação. A cobertura das 48
  chamadas e de todas as combinações foi validada com provedor controlado.
  Snapshot preservado em `artifacts/performance-review/sdk-partial-evidence.json`.
- Conferência visual no Windows, aplicação em código-fonte com catálogo isolado:
  tabela por mediana, recomendação destacada, rolagem, ações visíveis e botão
  **Aplicar configuração recomendada**. Clique real confirmou 3/1 na mensagem de
  estado da prévia. Os valores da prévia são artificiais; não são resultado do provedor.
- Ruff, formatação e `git diff --check` passaram. Os testes gerais de interface
  ainda esperam elementos do desenho anterior: a primeira falha reproduzida é
  `AttributeError: App has no attribute force_button`. Esse botão já havia sido
  substituído pelas ações avançadas no redesenho presente no workspace antes desta
  revisão. A suíte geral não está aprovada; não se tratou esse resultado como sucesso.
- Não foram executadas as 192/384 transferências da calibração na playlist real,
  nem recriado o executável distribuído. Nenhum teste sintético estabelece qual
  paralelismo é melhor para a playlist no provedor externo.

A revisão automática de aprovação rejeitou a remoção da pasta temporária com a
mensagem `blocked by policy`, sem justificativa adicional. Os processos do ensaio
foram encerrados; a pasta `C:\Users\jvpro\AppData\Local\Temp\spotano-sdk-benchmark-pc85mhxx`
ficou preservada. O snapshot foi copiado antes da interrupção e mantém o estado
`running` daquele instante; não deve ser confundido com um teste concluído.
