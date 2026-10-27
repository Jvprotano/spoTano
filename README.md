# spoTano

Sua música, com você. Aplicação desktop open-source para acompanhar playlists do
Spotify, manter uma biblioteca MP3 organizada e exportar diferenças para um
pendrive ou outra pasta. Interface em português, sem conta spoTano ou IA paga.

## Versão 1.3.0

Pacote local desta implementação: `dist/spoTano-1.3.0-windows-x64.zip`.

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
íntegros continuam sendo reutilizados em **Baixar novas**.

A classificação ocorre em paralelo à busca do áudio, com consultas deduplicadas
por artista. Os votos das tags contam na escolha da categoria. O cache de gêneros
foi versionado; **Reclassificar gêneros** renova as fontes, respeitando os limites
de consulta. Colaboradores e evidências específicas de faixa podem complementar
o artista principal. Last.fm é opcional: configure uma chave nas Configurações,
ou `LASTFM_API_KEY` no ambiente. Sem chave, o fluxo principal continua funcionando.
A chave configurada fica no catálogo local e em seu backup, e é omitida dos logs.

Em **Biblioteca → Fonte do áudio**, consulte as opções, confira duração e edição,
abra o vídeo e escolha a gravação completa. Também é possível colar a URL do
YouTube. **Baixar esta gravação** substitui somente essa faixa após validação.
**Automática** remove a escolha para downloads futuros. **Corrigir artista**
define uma categoria para o artista; a correção individual da faixa tem prioridade.

Downloads e conversões têm limites separados. Para comparar com o teste anterior,
use **3 downloads e 3 conversões em paralelo**, configuração que funcionou melhor
no teste real do usuário. As preferências salvas são preservadas. Quatro downloads devem ser
avaliado com o próprio provedor; mais conversões podem disputar CPU. A saída
continua MP3 CBR 192 kbps / 44,1 kHz / estéreo, com ID3v2.3 e gênero quando os metadados estão habilitados.
Correções de categoria atualizam tags, hash e exportação sem baixar novamente.

A troca de caminho ou de conteúdo deixa uma transição recuperável no catálogo.
Depois de validar o novo MP3, versões anteriores conhecidas vão para a lixeira;
uma interrupção é reconciliada na próxima abertura. **Revisar cópias antigas**
lista arquivos físicos sem vínculo para uma movimentação explícita à lixeira.
Arquivos desconhecidos ou alterados continuam protegidos.

Cada lote salva `runs/<id>/events.jsonl` e `summary.json` na pasta de dados,
independentemente do texto visível no painel. As métricas incluem duração,
configuração, versões, consultas, cache, candidatos, tempos por fase e falhas.
Use **Configurações → Abrir métricas das execuções** depois do próximo teste.
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
4. Em **Configurações**, clique **Preparar downloads (FFmpeg + Deno)** uma vez.
   Requer internet e espaço em disco; não exige ambiente de desenvolvimento.
5. Cole uma URL pública na aba **Playlists** e clique **Importar playlist**.
   Nome e faixas são consultados imediatamente, sem baixar áudio. Marque uma ou
   mais playlists, clique **Baixar tudo**, confira a prévia e confirme.

O binário ainda não tem assinatura de código. Use a distribuição deste
repositório e confira `SHA256SUMS.txt` com `Get-FileHash` se desejar.

## Como usar

### Adicionar e atualizar playlists

Aceita links `https://open.spotify.com/playlist/<id>`, inclusive parâmetros de
compartilhamento e prefixo de idioma. Adicione quantas playlists precisar.
**Importar playlist** busca nome, total e faixas em segundo plano e só salva após
uma consulta completa. Um link já importado orienta a usar a playlist existente.
As colunas mostram o total de faixas, quantas têm arquivo local e a data do último
download concluído; selecionar uma linha mostra a última consulta e observações.

Use as caixas da coluna **Marcar** (ou Espaço), **Marcar todas** e **Desmarcar**.
**Atualizar selecionadas** consulta somente as marcadas, salva a lista atual e
verifica diferenças e integridade local. **Não baixa nem remove áudios.** Está
disponível mesmo antes do primeiro download. Depois da consulta, quando houver
mudanças ou pendências, aparecem mais duas ações além de **Baixar tudo**:

- **Baixar novas**: baixa faixas novas, ausentes ou inválidas e mantém na biblioteca
  os arquivos das faixas que saíram da playlist.
- **Baixar e remover excluídas**: baixa as pendências e move para a lixeira local
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

**Baixar tudo** usa a lista já importada, sem consultar novamente
o Spotify, e força os downloads apenas das playlists marcadas, deduplicando faixas
compartilhadas entre elas. A prévia informa a data da última leitura. Para buscar
mudanças na playlist, use **Atualizar selecionadas**. Os
arquivos anteriores são mantidos até o novo MP3 ser validado. Um download que
falha não impede os seguintes; o erro aparece na Biblioteca. Se o arquivo antigo
continua íntegro, ele permanece utilizável; **Baixar novas**
o reutiliza. Use **Baixar tudo** ou **Associar MP3 local** para tentar substituir esse arquivo depois.

O estado persiste entre execuções. Fechar durante uma operação solicita
cancelamento. Ao abrir novamente, **Atualizar selecionadas** verifica o que falta e
**Baixar novas** retoma as pendências. A leitura
incompleta de qualquer playlist aborta toda a prévia e preserva o snapshot anterior.
Playlists vazias completas são válidas; itens indisponíveis tornam remoções
ambíguas e bloqueiam aquela atualização por segurança.

Em **Configurações → Downloads em paralelo**, escolha de 1 a 4 músicas simultâneas
(padrão: 2). Cada processo prepara os clientes uma vez e os reutiliza até terminar
o lote, com temporários isolados e timeout de 480 segundos por faixa. Cancelar
encerra os processos e conversores ativos; um timeout reinicia somente o mecanismo
afetado para a próxima faixa. O perfil MP3 e a validação dos arquivos são mantidos.
Metadados indisponíveis, como o ID do álbum no backend gratuito, permanecem ausentes
no catálogo e não provocam uma segunda consulta ao Spotify por música.

### Acompanhar o progresso

O painel **Progresso em tempo real**, visível em todas as abas, mantém linhas com
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
recentes por sessão. **Ampliar logs** aumenta o painel para acompanhar operações
longas; **Reduzir logs** devolve espaço à lista. A leitura dos logs não exige abrir
o Histórico.
Com downloads paralelos, cada etapa do mecanismo identifica o artista e a música.
O painel informa quantas faixas finalizaram e mede preparação, processamento,
tempo total por faixa e duração do lote. A busca e disponibilidade dos provedores
ainda variam; paralelismo não garante um tempo fixo para uma playlist.
No Windows, os subprocessos do mecanismo, incluindo FFmpeg e Deno, executam
em segundo plano sem abrir janelas de terminal.

### Organizar e corrigir

O padrão é **Download simples**: todas as músicas ficam soltas na pasta `Music`,
sem classificação, pastas por artista ou metadados extras no MP3. Em **Playlists →
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
reaplicar sem baixar áudio novamente, use **Configurações → Aplicar opções às
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

Na Biblioteca, selecione uma faixa, escolha a categoria e clique **Corrigir
categoria**. A correção persiste e tem prioridade. **Automática** remove a
correção. **Reclassificar gêneros** nas Configurações atualiza as classificações
automáticas. Selecione **Artistas** sem **Categoria** para usar pastas por artista,
ou desmarque ambas para manter as músicas juntas.
Trocar organização reaproveita os áudios; não cria downloads.
Arquivos em **Outros** também podem ser corrigidos automaticamente durante uma
atualização que reutiliza o áudio. Para corrigir os já baixados imediatamente,
use **Configurações → Reclassificar gêneros**; correções manuais têm prioridade.

**Associar MP3 local** permite usar uma gravação que você já possui e tem direito
de utilizar. Ela é convertida para o mesmo perfil automotivo e ligada à faixa
selecionada, sem precisar encontrar uma correspondência em outro provedor.

### Exportar para pendrive

1. Em **Pendrive e exportação**, escolha a organização da saída:
   **Coleção unificada** (`spoTano/Categoria/Música.mp3`), **Uma pasta por playlist**
   (`spoTano/Playlist/Categoria/Música.mp3`) ou **Pastas por grupo**
   (`spoTano/Grupo/Categoria/Música.mp3`). Com organização por artista, o artista
   ocupa o lugar da categoria. Os exemplos na tela mostram as pastas reais.
   Novos catálogos usam **Uma pasta por playlist** por padrão; configurações
   existentes são mantidas. A coluna **Pasta na exportação** e o aviso na aba
   Playlists mostram se as coleções ficarão separadas ou juntas.
2. Para personalizar, marque playlists na aba Playlists e clique **Pasta / grupo…**.
   O mesmo nome reúne playlists no modo por grupo; no modo por playlist, define
   o nome individual da pasta. Nomes iguais de playlists recebem um sufixo para
   evitar misturar coleções. Um nome vazio restaura o original / **Sem grupo**.
3. Conecte o dispositivo, abra **Pendrive e exportação** e clique **Detectar
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
