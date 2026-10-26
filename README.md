# spoTano

Sua música, com você. Aplicação desktop open-source para acompanhar playlists do
Spotify, manter uma biblioteca MP3 organizada e exportar diferenças para um
pendrive ou outra pasta. Interface em português, sem conta spoTano ou IA paga.

## Windows: baixar e abrir

1. Abra a página de [Releases](https://github.com/Jvprotano/spoTano/releases/latest).
2. Baixe `spoTano-1.0.0-windows-x64.zip` e extraia **a pasta inteira** para um local
   como `C:\Aplicativos\spoTano`. Não execute de dentro do ZIP.
3. Abra **spoTano.exe**. Python e as bibliotecas já estão no pacote.
4. Em **Configurações**, clique **Preparar downloads (FFmpeg + Deno)** uma vez.
   Requer internet e espaço em disco; não exige ambiente de desenvolvimento.
5. Adicione uma URL de playlist pública na aba **Playlists** e clique
   **Atualizar biblioteca**. Confira as inclusões, saídas e downloads e confirme.

O binário ainda não tem assinatura de código. Use a distribuição deste
repositório e confira `SHA256SUMS.txt` com `Get-FileHash` se desejar.

## Como usar

### Adicionar e atualizar playlists

Aceita links `https://open.spotify.com/playlist/<id>`, inclusive parâmetros de
compartilhamento e prefixo de idioma. Adicione quantas playlists precisar.
**Atualizar** lê todas, mostra as diferenças e baixa apenas faixas ausentes ou
cujo arquivo falhou na verificação. Uma faixa com o mesmo Spotify ID em várias
playlists ocupa um só arquivo. Remover de uma delas não afeta as demais.

**Baixar tudo novamente** faz nova consulta e força todos os downloads. Os
arquivos anteriores são mantidos até o novo MP3 ser validado. Um download que
falha não impede os seguintes; o erro aparece na Biblioteca. Se o arquivo antigo
continua íntegro, ele permanece utilizável; **Atualizar** o reutiliza. Use o modo
forçado ou **Associar MP3 local** para tentar substituir esse arquivo depois.

O estado persiste entre execuções. Fechar durante uma operação solicita
cancelamento. Ao abrir novamente, Atualizar detecta o que ainda falta. A leitura
incompleta de qualquer playlist aborta toda a prévia e preserva o snapshot anterior.
Playlists vazias completas são válidas; itens indisponíveis tornam remoções
ambíguas e bloqueiam aquela atualização por segurança.

### Organizar e corrigir

A classificação por gênero vem ativada. Categorias incluem Sertanejo, Pagode e
Samba, MPB, Rock e Metal, Pop, Eletrônica, Rap e Hip-Hop, Forró, Gospel e outras.
Gêneros disponíveis são agrupados; quando faltam, a consulta gratuita ao
MusicBrainz usa o artista e um cache de 90 dias. Isso não garante a classificação
de cada música. Sem evidência suficiente, o destino é **Outros**.

Na Biblioteca, selecione uma faixa, escolha a categoria e clique **Corrigir
categoria**. A correção persiste e tem prioridade. **Automática** remove a
correção. **Reclassificar gêneros** nas Configurações atualiza as classificações
automáticas. Desative **Organizar por gênero** para usar pastas por artista.
Trocar organização reaproveita os áudios; não cria downloads.

**Associar MP3 local** permite usar uma gravação que você já possui e tem direito
de utilizar. Ela é convertida para o mesmo perfil automotivo e ligada à faixa
selecionada, sem precisar encontrar uma correspondência em outro provedor.

### Exportar para pendrive

1. Conecte o dispositivo, abra **Pendrive e exportação** e clique **Detectar
   pendrives**, ou use **Escolher pasta**.
2. Clique **Conferir e exportar**. A prévia mostra cópias, arquivos reutilizados,
   espaço necessário e arquivos antigos que irão para a lixeira.
3. Confirme. O programa verifica cada cópia por SHA-256 e informa o caminho final.
4. Ejete o pendrive com segurança pelo Windows.

O destino fica em `<pasta escolhida>\spoTano\`. Só arquivos gerenciados pelo
manifesto `.spotano-manifest.json` são substituídos ou movidos. Conflitos com
arquivos desconhecidos ou modificados bloqueiam a exportação; nada fora da pasta
spoTano é gerenciado. Se faltar alguma música, a exportação é bloqueada até você
resolver a biblioteca, evitando produzir uma coleção incompleta silenciosamente.

Exportações seguintes conferem hashes e copiam somente mudanças. Pastas mantêm
a organização por gênero ou artista. Áudios que saem de todas as playlists
deixam a coleção exportada após confirmação; as versões antigas ficam em
`spoTano\.spotano-trash\<lote>`. Essa lixeira ocupa espaço e pode aparecer no
rádio; esvazie manualmente após conferir ou mova-a para o computador.

### Kia Cerato 2011 e rádios antigos

Perfil: **MP3 CBR 192 kbps, 44,1 kHz, estéreo, ID3v2.3, sem capas, nomes ASCII e
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
    Sertanejo/Artista - Musica [SpotifyID].mp3
    Rock e Metal/Artista - Musica [SpotifyID].mp3
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
