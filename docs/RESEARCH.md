# Pesquisa e decisões técnicas — 26/10/2026

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
do MusicBrainz > Outros. Agrupamento explícito de subgêneros em categorias
abrangentes, com termos brasileiros antes de termos genéricos. Consultas enviam
apenas artista, exigem nome exato e score >=95, cacheiam 90 dias, usam User-Agent
identificável e intervalo >=1,1 s; três falhas suspendem consultas naquele lote.
Tags de artista não representam perfeitamente cada faixa. Sem IA paga.

Referências: [API MusicBrainz](https://musicbrainz.org/doc/MusicBrainz_API),
[limites](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).

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
