# spoTano

Sua música, com você. Aplicação desktop open-source para acompanhar playlists do
Spotify, manter uma biblioteca MP3 organizada e exportar diferenças para um
pendrive ou outra pasta. Interface em português, sem conta spoTano ou IA paga.

## Versão 2.4.0

Pacote local: `dist/spoTano-2.4.0-windows-x64.zip`. Extraia a pasta inteira e abra
`spoTano.exe`.

Conversão rápida pelo Windows como padrão, com recuperação automática pelo LAME.
Em Configurações → Desempenho → Conversão MP3, escolha **Rápida · Windows** ou
**Tradicional · LAME**. Ambos mantêm MP3 CBR 192 kbps, 44,1 kHz e estéreo;
os encoders usam algoritmos diferentes. A escolha vale para novos downloads e
importações, sem reconverter sua biblioteca.

Na comparação local com três faixas completas e duas conversões simultâneas,
o caminho rápido reduziu o tempo em **38,7%**, incluindo finalização e validação.
Também foram recuperadas as três falhas de correspondência restantes do log.
[Análise e limitações da 2.4.0](docs/RELEASE-2.4.0-VALIDATION.md).

Biblioteca com filtro por categoria combinado à busca e ao estado. Marque músicas
pelos checkboxes e use **Ajustar marcadas…** para aplicar uma categoria às faixas
ou aos seus artistas principais, inclusive voltar à classificação Automática.
O checkbox do cabeçalho alterna todas as músicas visíveis; Espaço marca a linha
em foco e Ctrl+A alterna todas. Ao filtrar, músicas ocultadas são desmarcadas.
Por artista também afeta outras faixas e futuras importações; correções individuais
têm prioridade. Fonte do áudio e associação de MP3 permanecem individuais.

Playlists com ações diretas na própria linha: atualizar do Spotify, detalhes,
pasta/grupo e remover. O checkbox do cabeçalho marca ou desmarca todas; seleção
parcial tem indicador próprio. **Baixar / retomar**, **Baixar tudo** e **Baixar e
remover** ficam sempre visíveis e são habilitados ao marcar playlists. As opções
de download continuam em Configurações → Downloads.

Teste de configuração recomendada com dois modos: **rápido** como ação principal
e **completo** para comparar todas as combinações. Usa uma playlist padrão,
mostra ranking por desempenho, identifica a configuração inicial e oferece
**Aplicar configuração recomendada**. A configuração só muda ao aplicar.
Conferência do pacote: [validação da 2.4.0](docs/RELEASE-2.4.0-VALIDATION.md).

Novo ícone próprio: uma nota musical com seta, em verde e marfim, representa sua
música com você. Aparece no executável, nos atalhos criados para ele, nas janelas
e na barra de tarefas do Windows. A distribuição continua portátil.

A interface foi recriada para dar mais espaço às músicas e reduzir as decisões em
cada tela:

- **Playlists**: adicione pelo botão no topo, marque as playlists e escolha o
  download no rodapé. Os ícones de cada linha atualizam, mostram detalhes,
  definem pasta/grupo e removem aquela playlist. Atualizar consulta mudanças,
  sem baixar nem remover áudio.
- **Biblioteca**: busque música/artista, filtre por estado/categoria, marque músicas
  para ajustar em massa ou abra **Detalhes e
  ajustes** (ou Enter/duplo clique) para corrigir a categoria ou escolher a fonte do áudio.
- **Exportar**: escolha o destino e a organização, confira a prévia e confirme.
  Inclui todas as playlists importadas; conclua os downloads antes de exportar.
- **Configurações**: Downloads, Desempenho, Manutenção e Sobre. As ferramentas de
  limpeza, backup, diagnóstico e fontes opcionais ficam na Manutenção.
- **Ver atividade** abre os logs quando necessário. A etapa atual, o progresso
  real do lote e o cancelamento continuam acessíveis em qualquer área.

A retomada, as preferências existentes e a proteção de arquivos são mantidas.
Plano e conferência: [redesenho desktop](docs/ui-redesign/PLAN.md) e
[validação da versão](docs/ui-redesign/VALIDATION.md).

O extrator de mídia e as conexões de consulta são reutilizados. A classificação
confere a gravação nos catálogos iTunes e Deezer antes de consultar gêneros de
artistas no MusicBrainz/Wikidata. Rótulos amplos como Pop têm prioridade menor que
evidências específicas. Homônimos são desambiguados por identidade externa;
colaboradores conflitantes não decidem pela ordem dos créditos. Há cache,
limites por fonte e orçamento de 20 segundos para as consultas de cada faixa.
Uma indisponibilidade pode deixar a classificação pendente para outra atualização.

Os nomes exportados ficam como `Artista - Música.mp3`, sem o Spotify ID.
Nomes iguais recebem numeração para preservar as gravações. O ID permanece no
catálogo, no manifesto e nos caminhos internos. Ao atualizar uma exportação
antiga, os nomes anteriores conhecidos são guardados na lixeira gerenciada.
Com **Categoria** habilitada, downloads incrementais revisam classificações automáticas antigas
sem baixar o áudio novamente; correções manuais continuam tendo prioridade.

A busca usa páginas menores e compara artista, título, duração e edição, sem
consultar vídeos individuais apenas para contar visualizações. A pesquisa amplia
os resultados quando necessário e tenta até três gravações compatíveis em caso
de falha de extração. Correspondências validadas ficam em cache por Spotify ID e
metadados; URLs temporárias de mídia são renovadas na extração. Arquivos locais
íntegros continuam sendo reutilizados em **Baixar / retomar**.

Cada execução guarda `events.jsonl`, `summary.json`, `report.txt` e `failures.csv`
na pasta de dados, em `runs/<execução>/`. O relatório identifica música, artista,
playlist, resultado e motivo das pendências; inclui faixas canceladas ou ainda
não iniciadas. A fila fica registrada antes do download. **Ver relatório**, no
resultado do lote, abre essa pasta; o diagnóstico também fica disponível em
Configurações. A busca registra os candidatos rejeitados e o critério da rejeição.
Créditos de duplas separados e marcações de edição entre parênteses são reconhecidos.
A conversão mantém o perfil MP3 e reduz o log interno do FFmpeg para evitar trabalho
de depuração desnecessário.

Para conferir uma execução anterior sem alterar o catálogo:

```powershell
.venv\Scripts\python.exe scripts\audit_download_run.py "CAMINHO\runs\EXECUÇÃO" --output "CAMINHO\relatorio" --catalog "CAMINHO\library.sqlite3"
```

O parâmetro `--catalog` é opcional e verifica os arquivos atuais, seus hashes e o
perfil MP3. A pasta de saída deve ser diferente da execução original.

A classificação ocorre em paralelo à busca do áudio, com consultas deduplicadas
por artista. Os votos das tags contam na escolha da categoria. O cache de gêneros
foi versionado; **Reclassificar gêneros** renova as fontes, respeitando os limites
de consulta. Colaboradores e evidências específicas de faixa podem complementar
o artista principal. Last.fm é opcional: configure uma chave nas Configurações,
ou `LASTFM_API_KEY` no ambiente. Sem chave, o fluxo principal continua funcionando.
A chave configurada fica no catálogo local e em seu backup, e é omitida dos logs.

Em **Biblioteca → Detalhes e ajustes → Fonte do áudio**, consulte as opções, confira duração e edição,
abra o vídeo e escolha a gravação completa. Também é possível colar a URL do
YouTube. **Baixar esta gravação** substitui somente essa faixa após validação.
**Automática** remove a escolha para downloads futuros. **Aplicar ao artista**
define uma categoria para o artista; a correção individual da faixa tem prioridade.

Downloads e conversões têm limites separados. Para comparar com o teste anterior,
use **3 downloads e 3 conversões em paralelo**, configuração que funcionou melhor
no teste real do usuário. As preferências salvas são preservadas. Quatro downloads devem ser
avaliado com o próprio provedor; mais conversões podem disputar CPU. A saída
continua MP3 CBR 192 kbps / 44,1 kHz / estéreo, com ID3v2.3 e gênero quando os metadados estão habilitados.
Correções de categoria atualizam tags, hash e exportação sem baixar novamente.

Em **Configurações → Desempenho**, escolha **Teste rápido…** ou **Teste completo…**.
Não é necessário ter playlists importadas: o teste usa por padrão a
[playlist de teste](https://open.spotify.com/playlist/0aoPyrSGmKxpwxzN9NDr7c).
Se quiser outra, altere **Playlist usada no teste** e clique **Salvar playlist de teste**.
**Usar playlist padrão** restaura o endereço inicial. A playlist é consultada sem
ser importada na biblioteca pessoal.

Comece pelo **rápido**, a ação principal: quatro músicas, duas rodadas e os perfis
1/1, 2/2, 3/3 e 4/4 (downloads/conversões). Sua configuração atual também participa
quando for diferente desses perfis. São **8 a 10 lotes, 32 a 40 downloads reais**,
contra 48 lotes/384 downloads do completo com oito músicas. O rápido fornece uma
recomendação inicial entre esses perfis; não cobre todas as combinações.

O **completo** cobre **todas as 16 combinações** de 1–4 downloads × 1–4 conversões,
com três rodadas e amostra de 4 ou 8 músicas (padrão: 8): **48 lotes, 192 ou 384
downloads reais**. Use-o para explorar ajustes separados de downloads e conversões.
Pode levar dezenas de minutos ou mais. O rápido reduz o trabalho; a duração de
ambos depende da máquina, rede e provedor, sem prazo fixo garantido.

Nos dois modos, a amostra deduplica faixas e distribui durações. A ordem das
configurações varia, com inversão na segunda rodada; a ordem das músicas é igual
para todas as configurações de uma rodada. Usa o fluxo real, opções fixadas no início
e caches locais vazios, em catálogos temporários na mesma unidade. Preserva fontes
manuais, correções, áudios e caches da biblioteca original. Use o computador ocioso
e ligado à tomada; permite cancelar pelos controles habituais.

O resultado traz uma **tabela ordenada pela mediana do tempo, do menor para o maior**,
com músicas/minuto, variação e destaque para a recomendação. A recomendação exige
rodadas completas, sem falhas, com variação `(máximo − mínimo) / mediana` de até
15% no rápido (duas rodadas) ou 25% no completo (três rodadas). O rápido usa um
limite mais estrito porque tem menos observações. Esses limites são regras práticas
para rejeitar medições instáveis, sem garantia estatística. Dentro de 5% do menor tempo, prefere menos processos entre
os resultados estáveis; não recomenda uma configuração estável muito mais lenta
quando as mais rápidas foram instáveis. Falhas e rodadas incompletas aparecem sem
classificação. **Aplicar configuração recomendada** salva os dois valores juntos;
nada muda automaticamente. Se as opções usadas no teste mudaram, é necessário repeti-lo.

**Último resultado** reabre a tabela; **Medições por rodada** mostra tempos individuais,
falhas, mínimo/máximo e o método. Relatórios, ranking, ordem de execução e métricas
por fase ficam em `benchmarks/<id>/`, inclusive em testes cancelados. Resultados do
método antigo por etapas podem ser consultados, mas exigem novo teste para aplicação.
MP3s e catálogos temporários são removidos a cada lote. Os tempos incluem preparação
dos processos, que pesa mais em amostras pequenas; para coleções maiores, prefira 8 músicas.
Rede, provedor, caches externos e outros programas podem afetar o resultado; ele vale
para essa amostra e opções, sem garantia do tempo de uma playlist inteira.
Revisão do método: [teste de configuração recomendada](docs/PERFORMANCE-CALIBRATION.md).

A troca de caminho ou de conteúdo deixa uma transição recuperável no catálogo.
Depois de validar o novo MP3, versões anteriores conhecidas vão para a lixeira;
uma interrupção é reconciliada na próxima abertura. **Revisar cópias antigas**
lista arquivos físicos sem vínculo para uma movimentação explícita à lixeira.
Arquivos desconhecidos ou alterados continuam protegidos.

Cada lote salva `runs/<id>/events.jsonl` e `summary.json` na pasta de dados,
independentemente do texto visível no painel. As métricas incluem duração,
configuração, versões, consultas, cache, candidatos, tempos por fase e falhas.
Use **Configurações → Manutenção → Abrir métricas das execuções** depois do próximo teste.
O final diferencia conclusão completa e conclusão com falhas. O erro original e
sua causa são preservados sem cookies, chaves ou URLs assinadas.

Para uma comparação de primeiro download, **Limpar cache de correspondências**
remove apenas as escolhas automáticas; preserva MP3s e fontes manuais. Use **Baixar
tudo** para substituir os áudios, ou um diretório de dados novo se quiser uma
biblioteca de testes completamente isolada. Limpar o log visível não limpa caches.
Os tempos reais da playlist de 200 músicas dependem de rede, gravações e provedor;
os benchmarks sintéticos não são uma previsão desse tempo.

Plano e validação: [refinamento após o teste real](docs/EXECUTION-REFINEMENT.md)
e [otimização anterior](docs/EXECUTION-OPTIMIZATION.md).

## Windows: baixar e abrir

1. Use o pacote local indicado acima. Versões publicadas também ficam em
   [Releases](https://github.com/Jvprotano/spoTano/releases/latest).
2. Extraia **a pasta inteira** do ZIP para um local
   como `C:\Aplicativos\spoTano`. Não execute de dentro do ZIP.
3. Abra **spoTano.exe**. Python e as bibliotecas já estão no pacote.
4. Em **Configurações → Downloads**, clique **Preparar downloads** uma vez.
   Requer internet e espaço em disco; não exige ambiente de desenvolvimento.
5. Em **Playlists → Adicionar playlist**, cole uma URL pública e clique **Importar playlist**.
   Nome e faixas são consultados imediatamente, sem baixar áudio. Marque uma ou
   mais playlists, clique **Baixar / retomar**, confira a prévia e confirme.

O binário ainda não tem assinatura de código. Use a distribuição deste
repositório e confira `SHA256SUMS.txt` com `Get-FileHash` se desejar.

## Como usar

### Adicionar e atualizar playlists

Aceita links `https://open.spotify.com/playlist/<id>`, inclusive parâmetros de
compartilhamento e prefixo de idioma. Adicione quantas playlists precisar.
**Importar playlist** busca nome, total e faixas em segundo plano e só salva após
uma consulta completa. Um link já importado orienta a usar a playlist existente.
As colunas mostram o total de faixas, quantas têm arquivo local e a data do último
download concluído; um duplo clique na linha abre a última consulta, o link e as observações.

Use as caixas da primeira coluna (ou Espaço). A caixa no cabeçalho marca ou
desmarca todas; **Ctrl+A**, com foco na lista, faz o mesmo.
O ícone **↻** da linha (**F5**) consulta somente aquela playlist, salva a lista atual e
verifica diferenças e integridade local. **Não baixa nem remove áudios.** Está
disponível mesmo antes do primeiro download. Para baixar os áudios:

- **Baixar / retomar**: sempre disponível ao marcar playlists. Baixa faixas novas,
  ausentes e pendências de uma execução interrompida, reaproveitando as concluídas.
  Mantém na biblioteca os arquivos das faixas que saíram da playlist.
- **Baixar e remover**: baixa as pendências e move para a lixeira local
  os arquivos das faixas que saíram. Preserva músicas usadas ou mantidas por outras
  playlists. Se algum download falhar, nenhuma remoção é executada.

As duas ações usam a última lista salva, sem outra consulta ao Spotify. A prévia
mostra os downloads e os caminhos que serão movidos. É possível baixar novas agora
e escolher remover as excluídas depois, inclusive após reiniciar o aplicativo.
Uma faixa com o mesmo Spotify ID em várias playlists ocupa um só arquivo interno.
Remover de uma delas não afeta as demais.

A prévia lista as playlists incluídas, inclusões e saídas em relação aos downloads
mantidos, arquivos reutilizados e downloads necessários. Na primeira vez, todas
as faixas são inclusões. Uma falha parcial preserva a referência anterior para
a próxima comparação; cada playlist conclui independentemente das demais. Para
catálogos antigos, a referência inicial é a última lista salva, indicada na prévia,
pois a versão anterior não registrava se todo o download havia terminado.

**Baixar tudo**, sempre visível no rodapé, usa a lista já importada, sem consultar novamente
o Spotify, e força os downloads apenas das playlists marcadas, deduplicando faixas
compartilhadas entre elas. A prévia informa a data da última leitura. Para buscar
mudanças na playlist, use **Atualizar do Spotify**. Os
arquivos anteriores são mantidos até o novo MP3 ser validado. Um download que
falha não impede os seguintes; o erro aparece na Biblioteca. Se o arquivo antigo
continua íntegro, ele permanece utilizável. **Baixar / retomar** repete a
substituição pendente, sem repetir as substituições que já terminaram.

O estado persiste entre execuções. A fila inteira é salva antes de começar;
cada MP3 validado é registrado separadamente. Fechar durante uma operação solicita
cancelamento. Após cancelamento, queda de conexão ou encerramento abrupto, abra
novamente e use **Baixar / retomar**: as playlists com pendências já ficam marcadas.
Não é preciso consultar o Spotify novamente para continuar a lista salva. Isso
também vale para **Baixar tudo**: arquivos antigos válidos não escondem as
substituições que ainda faltam. A faixa interrompida começa novamente; os MP3s já
concluídos são reutilizados. Arquivos modificados fora do aplicativo são preservados
para revisão, em vez de sobrescritos. A leitura
incompleta de qualquer playlist aborta toda a prévia e preserva o snapshot anterior.
Playlists vazias completas são válidas; itens indisponíveis tornam remoções
ambíguas e bloqueiam aquela atualização por segurança.

Em **Configurações → Desempenho → Downloads em paralelo**, escolha de 1 a 4 músicas simultâneas
(padrão: 2). Cada processo prepara os clientes uma vez e os reutiliza até terminar
o lote, com temporários isolados e timeout de 480 segundos por faixa. Cancelar
encerra os processos e conversores ativos; um timeout reinicia somente o mecanismo
afetado para a próxima faixa. O perfil MP3 e a validação dos arquivos são mantidos.
Metadados indisponíveis, como o ID do álbum no backend gratuito, permanecem ausentes
no catálogo e não provocam uma segunda consulta ao Spotify por música.

### Acompanhar o progresso

O painel **Ver atividade**, disponível em todas as áreas, mantém linhas com
horário: consulta e paginação do Spotify, conferência de arquivos, classificação,
posição na fila (ex.: 12/200), busca de áudio, transferência, conversão com FFmpeg,
validação MP3/SHA-256, caminho salvo e falhas. A interface continua utilizável para
ler os logs e solicitar cancelamento. Sem novas etapas por 10 segundos, informa
o tempo de espera e o limite da operação, sem afirmar que há transferência ativa.
A barra verde do lote mostra quantas faixas foram concluídas do total, com contagens
separadas de baixadas, falhas e arquivos reutilizados. Esse resumo permanece
visível enquanto outras músicas avançam e após cancelar. Durante transferência,
os logs mostram bytes recebidos, total e percentual quando o provedor informa
o tamanho; totais estimados recebem `~`. Sem total conhecido, mostram somente
os bytes recebidos. A conversão exibe o percentual fornecido pelo FFmpeg;
100% nessa etapa ainda exige tags e validação local antes de contar como baixada.
Busca e consulta de metadados não têm percentual inventado. Fora do lote, o
indicador animado informa que existe uma operação em andamento.
**Abrir pasta dos downloads**, no próprio painel, abre a biblioteca compartilhada
de áudios, organizada conforme as opções escolhidas. O resultado do download mostra o
caminho e um botão **Abrir pasta**; o resultado da exportação abre o destino real
da exportação. O atalho do painel continua disponível durante o download e após
cancelar, permitindo acessar os arquivos já salvos.
**Salvar logs…** salva o texto visível; o painel guarda até 10 mil linhas
recentes por sessão. **Ver atividade** abre o painel para acompanhar operações
longas; **Ocultar atividade** devolve espaço à lista. A leitura dos logs não exige abrir
o Histórico.
Com downloads paralelos, cada etapa do mecanismo identifica o artista e a música.
O painel informa quantas faixas finalizaram e mede preparação, processamento,
tempo total por faixa e duração do lote. A busca e disponibilidade dos provedores
ainda variam; paralelismo não garante um tempo fixo para uma playlist.
No Windows, os subprocessos do mecanismo, incluindo FFmpeg e Deno, executam
em segundo plano sem abrir janelas de terminal.

### Organizar e corrigir

O padrão é **Download simples**: todas as músicas ficam soltas na pasta `Music`,
sem classificação, pastas por artista ou metadados extras no MP3. Em **Configurações → Downloads →
Personalizar download**, marque apenas o que desejar, ou use **Marcar tudo** e
**Desmarcar tudo**:

- **Categoria**: classifica e cria pastas por gênero; desmarcada, não faz consultas
  de gênero, inclusive ao MusicBrainz.
- **Artistas**: cria pastas por artista. Com Categoria, usa `Categoria/Artista`;
  sozinha, usa apenas `Artista`.
- **Metadados**: grava título, artistas e os dados disponíveis de álbum, ano e
  número da faixa em ID3v2.3, sem capa. Desmarcada, não grava essas tags.

O nome do arquivo continua identificando artista, música e ID para evitar
colisões de títulos na pasta única. Os dados do catálogo usados para localizar o
áudio continuam disponíveis, independentemente das tags escolhidas.

As escolhas persistem e valem no próximo download ou exportação. Para
reaplicar sem baixar áudio novamente, use **Configurações → Downloads → Aplicar opções às
músicas já baixadas**. Alterações de tags preservam uma cópia anterior na lixeira.
Catálogos antigos também recebem o modo simples como padrão inicial; seus
arquivos são adaptados quando você executar uma dessas operações.

Cada opção mostra uma **estimativa fixa** de tempo extra por música: Categoria
**~8 s**, Artistas **menos de 1 s** e Metadados **~0,1 s**. São referências
aproximadas baseadas nos logs de teste revisados até 27/10/2026; não são
recalculadas a partir dos logs dos usuários. Cache, conexão, quantidade de artistas
e computador podem alterar os tempos reais. Os valores não estimam o download
inteiro nem a velocidade de cópia do pendrive.

Com Categoria habilitada, as categorias incluem Sertanejo, Pagode e
Samba, MPB, Rock e Metal, Pop, Eletrônica, Rap e Hip-Hop, Forró, Gospel e outras.
Gêneros disponíveis são agrupados; quando faltam, a consulta gratuita ao
MusicBrainz usa o artista; o Wikidata complementa quando não há gênero reconhecido
ou a primeira fonte falha. A correspondência exige nome/alias normalizado sem
ambiguidade e valida identificadores disponíveis. Gêneros confirmados têm cache
de 90 dias; ausência de resultado, de 1 dia. Falhas de rede são exibidas nos logs
e não são persistidas como ausência de gênero. Isso não garante a classificação
de cada música. Sem evidência suficiente, o destino é **Outros**.

As músicas aparecem na **Biblioteca** assim que a playlist é importada, antes
de baixar áudio. Você pode preparar as categorias primeiro ou corrigir depois:

- **Aplicar à faixa** altera apenas a música selecionada, com prioridade sobre
  a regra do artista e a classificação automática.
- **Aplicar ao artista** altera todas as músicas importadas do mesmo artista
  principal, respeitando as correções individuais, e vale para músicas futuras.

Com **Categoria** ativada, os arquivos já baixados mudam de pasta imediatamente,
sem novo download. As tags de gênero também são atualizadas quando **Metadados**
está ativo. Com Categoria desativada, a correção fica salva, sem criar pastas;
ative Categoria em **Personalizar download** e use **Aplicar opções às músicas
já baixadas** nas Configurações para reorganizar. Cópias já exportadas para o
pendrive são atualizadas na próxima exportação.

**Automática** remove a correção do escopo escolhido (faixa ou artista).
**Reclassificar gêneros** nas Configurações atualiza as classificações
automáticas. Selecione **Artistas** sem **Categoria** para usar pastas por artista,
ou desmarque ambas para manter as músicas juntas.
Trocar organização reaproveita os áudios; não cria downloads.
Arquivos em **Outros** também podem ser corrigidos automaticamente durante uma
atualização que reutiliza o áudio. Para corrigir os já baixados imediatamente,
use **Configurações → Manutenção → Reclassificar gêneros**; correções manuais têm prioridade.

**Associar MP3 local** permite usar uma gravação que você já possui e tem direito
de utilizar. Ela é convertida para o mesmo perfil automotivo e ligada à faixa
selecionada, sem precisar encontrar uma correspondência em outro provedor.

### Exportar para pendrive

1. Em **Exportar**, escolha a organização da saída:
   **Coleção unificada** (`spoTano/Categoria/Música.mp3`), **Uma pasta por playlist**
   (`spoTano/Playlist/Categoria/Música.mp3`) ou **Pastas por grupo**
   (`spoTano/Grupo/Categoria/Música.mp3`). Com organização por artista, o artista
   ocupa o lugar da categoria. Os exemplos na tela mostram as pastas reais.
   Novos catálogos usam **Uma pasta por playlist** por padrão; configurações
   existentes são mantidas. A prévia de pastas mostra como as coleções ficam organizadas.
2. Para personalizar, use **Exportar → Editar pastas / grupos…** e escolha uma playlist,
   ou use o ícone de pasta na própria linha da playlist (**Ctrl+G**).
   O mesmo nome reúne playlists no modo por grupo; no modo por playlist, define
   o nome individual da pasta. Nomes iguais de playlists recebem um sufixo para
   evitar misturar coleções. Um nome vazio restaura o original / **Sem grupo**.
3. Conecte o dispositivo, abra **Exportar** e clique **Detectar
   pendrives**, ou use **Escolher pasta**.
4. Clique **Conferir e exportar**. A prévia mostra os caminhos finais, cópias, arquivos reutilizados,
   espaço necessário e arquivos antigos que irão para a lixeira.
5. Confirme. O programa verifica cada cópia por SHA-256 e informa o caminho final.
6. Ejete o pendrive com segurança pelo Windows.

É possível escolher uma pasta no computador, sem pendrive. A exportação representa
**todas as playlists importadas**; as caixas controlam as ações de download e a
personalização de nomes. A biblioteca interna em `Music` continua compartilhada.
**Baixar duas playlists mantém seus áudios juntos nessa biblioteca**, conforme as opções de download. Para obter pastas separadas, exporte para uma pasta do computador ou
pendrive usando **Uma pasta por playlist**. Para reunir algumas playlists, escolha
**Pastas por grupo** e atribua o mesmo grupo às desejadas.
Na saída por playlist, uma faixa compartilhada aparece em cada pasta; por grupo,
aparece uma vez em cada grupo; na coleção unificada, uma vez no total. Mudar o modo
reutiliza áudios, sem baixá-los novamente. O novo modo só muda o destino após a
prévia e confirmação da exportação; as cópias antigas ficam na lixeira gerenciada.

O destino fica em `<pasta escolhida>\spoTano\`. Só arquivos gerenciados pelo
manifesto `.spotano-manifest.json` são substituídos ou movidos. Conflitos com
arquivos desconhecidos ou modificados bloqueiam a exportação; nada fora da pasta
spoTano é gerenciado. Se faltar alguma música, a exportação é bloqueada até você
resolver a biblioteca, evitando produzir uma coleção incompleta silenciosamente.

Exportações seguintes conferem hashes e copiam somente mudanças. A exportação
segue as opções escolhidas: pasta única, gênero, artista ou gênero/artista.
Áudios que saem de todas as playlists
deixam a coleção exportada após confirmação; as versões antigas ficam em
`spoTano\.spotano-trash\<lote>`. Essa lixeira ocupa espaço e pode aparecer no
rádio; esvazie manualmente após conferir ou mova-a para o computador.

### Kia Cerato 2011 e rádios antigos

Perfil: **MP3 CBR 192 kbps, 44,1 kHz, estéreo, ID3v2.3 quando habilitado, sem capas, nomes ASCII e
pastas rasas**. Prefira pendrive **FAT32**. O programa não formata discos e não
promete compatibilidade com todas as versões de rádio. Teste uma coleção pequena
no carro antes de exportar toda a biblioteca. A referência consultada é o
[manual Kia Forte 2011](https://www.kia.ca/content/dam/marketing/documents/en/owners/2011/11forte_en.pdf),
da mesma geração; o rádio brasileiro precisa de validação física.

## Dados, recuperação e backup

Por padrão: `%LOCALAPPDATA%\spoTano\`.

```text
spoTano/
  library.sqlite3       catálogo, associações, configurações e histórico
  Music/
    Artista - Musica [SpotifyID].mp3
  staging/              downloads em andamento, nunca considerados prontos
  trash/                versões substituídas e limpeza de órfãos
```

**Revisar faixas sem playlist** mostra órfãos antes de movê-los para a lixeira.
Remover uma playlist do acompanhamento não apaga arquivos. Não existe exclusão
definitiva automática nem limpeza automática de lixeira. Para recuperar áudio,
abra a pasta de dados e use **Associar MP3 local** no arquivo da lixeira.

O botão **Backup do catálogo** faz backup consistente do SQLite, mas não inclui
áudios. Para backup completo, feche a aplicação e copie a pasta de dados inteira.
Para restaurar, feche a aplicação e substitua a pasta por uma cópia completa.
Não restaure um banco antigo sobre um banco aberto com arquivos WAL ativos.
É possível escolher outro catálogo iniciando `spoTano.exe --data-dir D:\MinhaBiblioteca`.
Uma trava impede abrir duas janelas usando o mesmo catálogo simultaneamente.

Se o computador desligar durante uma operação, os arquivos anteriores ou suas
cópias de recuperação permanecem. Arquivos `.part` e pastas de staging de uma
execução encerrada abruptamente podem ser removidos manualmente com o programa
fechado. Em caso de divergência entre hash e arquivo, a aplicação preserva os
bytes e solicita revisão em vez de sobrescrever silenciosamente.

## Limitações e direitos de uso

- **Não baixa o stream protegido do Spotify.** O Spotify fornece metadados;
  o spotDL procura áudio em outros provedores. Ter Spotify Premium não concede
  automaticamente autorização para baixar gravações de terceiros.
- Use apenas conteúdo que você possa obter e usar legalmente, de acordo com os
  termos do provedor. Não há remoção de DRM nem mecanismo de contornar bloqueios.
- O backend gratuito upstream pode mudar ou parar; playlists privadas não são
  suportadas pela interface. É possível usar suas próprias credenciais da API
  oficial via `SPOTIPY_CLIENT_ID` e `SPOTIPY_CLIENT_SECRET` no ambiente; a aplicação
  não as grava no catálogo. Restrições atuais de acesso da API ainda se aplicam.
- Bloqueios, limites de consulta, músicas removidas e correspondências erradas
  continuam possíveis. Não há garantia de todos os títulos estarem disponíveis.
- O backend gratuito pode omitir álbum, capa, ISRC e gêneros; nome, artistas,
  identificador e duração disponíveis são preservados. Quando não expõe snapshot,
  uma edição simultânea mantendo o total pode não ser detectada.
- Deduplicação por Spotify ID, não por título: remasters/edições com IDs distintos
  podem gerar arquivos diferentes. Tags de artista não classificam perfeitamente
  cada faixa. Consultas de gênero dependem da disponibilidade do MusicBrainz.
- Não há agendamento automático; você inicia Atualizar e Exportar. Sem teste em
  rádio físico ou pendrive real, compatibilidade de hardware permanece pendente.

## Arquitetura e desenvolvimento

Python 3.11+ (3.12 recomendado), Tk/ttk e SQLite. Sem frontend ou servidor separado.
O [spotDL 4.6.0](https://github.com/spotDL/spotify-downloader) é uma dependência MIT
fixada; processos isolados fazem consultas/downloads com timeout e cancelamento.
O catálogo do spoTano controla referências, planos, integridade, lixeira e USB.
Veja [pesquisa](docs/RESEARCH.md), [validação](docs/VALIDATION.md) e
[avisos de licenças](THIRD_PARTY_NOTICES.md).

```powershell
git clone https://github.com/Jvprotano/spoTano.git
cd spoTano
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m spotano
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check spotano tests scripts launcher.py
.venv\Scripts\python scripts\build.py
```

No Linux, instale o pacote Tk da distribuição (ex.: `python3-tk`) e FFmpeg.
Detecção automática USB é Windows; seleção manual funciona nos outros sistemas.
O workflow testa Windows/Linux e publica o pacote Windows ao receber uma tag `v*`.
Dependências exatas usadas na entrega ficam em `requirements-lock.txt`.

## Licença

[GPL-3.0-or-later](LICENSE), com licenças próprias das dependências e ferramentas externas.
Nenhuma credencial, cache pessoal, catálogo real ou música é incluída no código.
