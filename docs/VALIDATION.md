# Validação — 26/10/2026

Evidências confirmadas nesta máquina Windows x64 com Python 3.12.3:

- 46 testes passando em CI Windows e Linux: referências compartilhadas, reinício, incremental, falhas
  parciais, download forçado com preservação, MP3 inválido, prévia obsoleta,
  correções, organização por artista, lixeira, cancelamento, backup SQLite,
  proteção de caminhos e manifesto, exportação incremental e conflitos.
- Teste de integração com áudio gerado localmente: FFmpeg real → worker isolado
  → validação MP3 → SQLite reaberto → exportação → segunda exportação sem cópias.
- Consulta real à playlist pública Today’s Top Hits: 50 faixas, total conferido.
  Somente metadados consultados; nenhuma música dessa playlist foi baixada.
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
