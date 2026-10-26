# Validação — 26/10/2026

Evidências confirmadas nesta máquina Windows x64 com Python 3.12.3:

- 45 testes passando na rodada completa: referências compartilhadas, reinício, incremental, falhas
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

A validação de hardware (pendrive físico e rádio Cerato 2011) não foi feita.
Serviços externos podem mudar, limitar consultas ou recusar áudio. Testes locais
não certificam download universal, matching perfeito ou disponibilidade futura.

Build empacotado, teste do executável e CI são registrados nesta página depois
da conclusão da publicação; não devem ser inferidos apenas dos testes Python.
