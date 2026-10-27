# Pesquisa e decisões técnicas — 26/10/2026

## Atualização 1.1.0 — busca e execução

O perfil novo usa `FastMatcher` sobre os provedores já instalados do spotDL,
sem chamar o desempate upstream por visualizações. Primeira pesquisa de dez
resultados, expansão limitada a trinta e fallback YouTube com extração plana.
Há validação explícita de artista/título/duração/edição, anos de edições nomeadas,
desempates por créditos e álbum e busca por ISRC quando fornecido. Resultados
ambíguos pedem escolha da gravação. São tentados no máximo três candidatos.
O cache persiste apenas a URL canônica e evidências de uma instalação validada,
indexadas pelo ID Spotify, fingerprint dos metadados e versão do matcher.

Em teste de metadados reais recuperados do Spotify para nove faixas do lote,
as pesquisas levaram 0,344–2,078 s, uma consulta por faixa, sem extrações para
visualizações. As buscas originais dessas faixas no log levaram 28–155 s.
Isso mede busca, não transferência/conversão nem validação auditiva da gravação.

A classificação roda junto ao download, sem o lock global durante rede. Um lock
por artista evita consultas repetidas; um limitador por fonte mantém o intervalo
de requisições. MusicBrainz preserva votos; gêneros brasileiros específicos têm
prioridade sobre rótulos genéricos conforme os pesos. Cache versão 3, correção por
artista explícita, override da faixa prioritário. Last.fm complementa artista/faixa
quando configurado. Não se infere gênero apenas pelo nome da faixa ou playlist.

Fontes consultadas novamente: [ytmusicapi Search](https://ytmusicapi.readthedocs.io/en/stable/reference/search.html),
[matching upstream](https://spotdl.github.io/spotify-downloader/reference/utils/matching/),
[Last.fm track tags](https://www.last.fm/api/show/track.getTopTags).

Os processos reutilizam o Downloader e possuem limites por fase além do timeout
total. Conversões usam slots protegidos por locks do sistema, liberados mesmo
quando o processo é encerrado. O padrão de duas conversões pode ser ajustado
separadamente dos downloads. Nenhuma nova dependência foi introduzida.

Instalação e tags usam journal em SQLite: preservar origem conhecida, registrar
intenção, instalar arquivo validado, confirmar catálogo/cache e remover a cópia
ativa anterior mantendo recuperação em trash. Alterações de tags recalculam SHA-256
e revisão. A recuperação não substitui um arquivo desconhecido ou modificado.

Medições e plano completo em [EXECUTION-OPTIMIZATION.md](EXECUTION-OPTIMIZATION.md).
As decisões históricas abaixo descrevem o fluxo anterior quando divergirem desta atualização.

## Soluções avaliadas

- [spotDL 4.6.0](https://github.com/spotDL/spotify-downloader): Python 3.11+, MIT.
  `Spotdl` encapsula `SpotifyClient`, tipos `Song` e `Downloader`; metadados vêm
  do Spotify e áudio de provedores como YouTube Music, via yt-dlp e FFmpeg.
  Já oferece CLI, web UI, `save`, `download`, `sync`, ID3, conversão e matching.
  A versão consultada usa SpotipyFree por padrão e permite API oficial.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp): excelente para extrair mídia,
  mas exigiria recriar correspondência de faixas e metadados Spotify.
- [beets](https://github.com/beetbox/beets): biblioteca/tagger maduro, com
  MusicBrainz e plugins; seu fluxo de importação e CLI acrescentaria outra
  camada de catálogo sem resolver diretamente o uso playlist → pendrive.

## Escolha

Usar spotDL como dependência fixada, sem fork: manutenção menor, licença simples
e atualização explícita. Não usar `spotdl sync` para excluir: o catálogo do
spoTano precisa controlar referências entre múltiplas playlists, prévias e USB.

SQLite guarda faixas, snapshots aceitos, associações, hashes, correções, settings,
cache de gêneros e histórico. Tk/ttk usa seletores nativos, sem serviço HTTP local.
O SDK roda em subprocessos com limite de tempo e cancelamento da árvore de
processos; a interface e o banco não ficam presos em retries do provedor.

Foi observado no código upstream que `Playlist.get_metadata` pode interromper
paginação sem erro quando `next` falha. Por isso a leitura do spoTano é própria,
através do cliente upstream: exige todas as páginas e total exato e compara
snapshot antes/depois quando disponível. Itens indisponíveis impedem aplicar
remoções ambíguas. Sem snapshot exposto pelo backend gratuito, essa comparação
não detecta edições simultâneas que mantenham o mesmo total.

## Gêneros

Prioridade: correção manual > metadados existentes > tags gratuitas de artista
do MusicBrainz > gêneros do Wikidata > Outros. Agrupamento explícito de subgêneros em categorias
abrangentes, com termos brasileiros antes de termos genéricos. Consultas enviam
artista, exigem nome/alias normalizado não ambíguo e score >=95 no MusicBrainz.
Resultados reconhecidos têm cache de 90 dias; negativos, de 1 dia; falhas não são
salvas como ausência. As requisições usam User-Agent identificável e intervalo
>=1,1 s; três falhas consecutivas suspendem aquela fonte no lote. No Wikidata,
usamos P136 e rótulos pt/en, exigimos grupo musical ou identificador musical,
e rejeitamos identificadores MusicBrainz/Spotify conflitantes.
Tags de artista não representam perfeitamente cada faixa. Sem IA paga.

Referências: [API MusicBrainz](https://musicbrainz.org/doc/MusicBrainz_API),
[limites](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).
Wikidata: [API](https://www.mediawiki.org/wiki/Wikibase/API) e
[formatos JSON](https://www.wikidata.org/wiki/Wikidata:Data_formats).

## Preparação e paralelismo de downloads

Na versão fixada do spotDL 4.6.0, `async_search_and_download` chama `reinit_song`
se `album_id` e outros campos forem `None`. O backend gratuito pode omitir álbum,
portanto isso gerava outra consulta ao Spotify por faixa. O adaptador passa valores
vazios apenas à representação do SDK, preservando ausências no catálogo; ISRC vazio
também é necessário para o gravador de tags. Um teste com o SDK real bloqueia toda
consulta de rede/Spotify e converte dois áudios sintéticos no mesmo mecanismo.

Cada executor usa um subprocesso persistente com um Downloader e event loop.
Padrão de dois executores; limite configurável de um a quatro. Cada processo recebe
uma tarefa de cada vez via arquivos JSON atômicos, emite eventos, pode ser encerrado
em timeout/cancelamento e é fechado ao terminar o lote. A fila fica limitada ao
número de executores. A biblioteca continua instalando apenas MP3s validados.

O SDK fixa temporários em `get_temp_path()/video-id.ext`, compartilhados por padrão.
No adaptador da versão fixada, os dois módulos que consomem esse caminho recebem
um diretório privado por processo. Não mudamos HOME nem a localização dos componentes
FFmpeg/Deno. Assim, gravações diferentes que correspondam ao mesmo vídeo não colidem.
Referência: [Downloader upstream](https://spotdl.github.io/spotify-downloader/reference/download/downloader/).

## Áudio automotivo

O [manual Kia Forte 2011](https://www.kia.ca/content/dam/marketing/documents/en/owners/2011/11forte_en.pdf)
documenta FAT12/16/32 e MP3 entre 8 e 320 kbps. É uma referência da mesma geração,
não uma certificação da unidade brasileira do Cerato. Perfil conservador:
MP3 CBR 192 kbps, 44,1 kHz, estéreo, ID3v2.3, sem capa, pastas rasas e nomes
ASCII. Nenhuma formatação de pendrive; validação no rádio físico continua necessária.

## Segurança operacional

Faixas usam Spotify ID como identidade. Edições/remasters com IDs diferentes
podem manter cópias separadas; não deduplicar por título evita confundir gravações.
Nenhuma exclusão definitiva automática. O catálogo local não é apagado ao sair
de uma playlist; limpeza explícita move órfãos para lixeira. Forçar download
preserva versão anterior até validar a nova. O destino tem manifesto SHA-256,
prévia e namespace `spoTano/`; arquivos estranhos/modificados bloqueiam sobrescrita.
