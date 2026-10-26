# Plano e evidência

- [x] Pesquisar spotDL 4.6.0, yt-dlp, beets e documentação Kia/MusicBrainz.
- [x] Escolher desktop Python/Tk + SQLite + adaptador isolado spotDL (MIT).
- [x] Implementar importação completa, plano incremental, downloads atômicos e recuperação.
- [x] Implementar gêneros/correções, biblioteca e exportação com manifesto e lixeira.
- [x] Implementar interface, configuração, cancelamento e diagnósticos.
- [x] Validar contratos com testes e fluxos reais possíveis neste ambiente.
- [ ] Empacotar Windows, publicar código e release públicos, conferir CI.

Decisões: nenhuma exclusão automática; prévias verificam revisão do banco. Downloads
substituem versões antigas apenas depois de validar MP3. Falhas na consulta completa
abortam o plano, sem alterar associação alguma. A exportação só gerencia spoTano/ e
preserva arquivos estranhos ou modificados pelo usuário. Não há credenciais no código.

Veja docs/RESEARCH.md para pesquisa e docs/VALIDATION.md para evidência final.
