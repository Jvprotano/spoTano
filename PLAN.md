# Plano e evidência

A versão local 2.1.0 reúne os testes rápido e completo de configuração recomendada,
playlist padrão, ranking e aplicação explícita. Método e limites em
[docs/PERFORMANCE-CALIBRATION.md](docs/PERFORMANCE-CALIBRATION.md).

Pendências conhecidas: adequar os testes antigos da interface ao redesenho e
validar a calibração completa com o provedor real nas condições de uso. Os testes
focados não substituem essas verificações. Commit/push e publicação não fazem
parte da geração do pacote local.

O redesenho desktop 2.0.0 está documentado em
[plano da nova interface](docs/ui-redesign/PLAN.md) e
[conferência prática](docs/ui-redesign/VALIDATION.md).

O plano das otimizações 1.1.0 está concluído em
[docs/EXECUTION-OPTIMIZATION.md](docs/EXECUTION-OPTIMIZATION.md), com medições e
[validação detalhada](docs/OPTIMIZATION-VALIDATION.md). A entrega 1.1.0 serviu de
referência para repetir o teste de dez faixas e avançar para duzentas.

- [x] Pesquisar spotDL 4.6.0, yt-dlp, beets e documentação Kia/MusicBrainz.
- [x] Escolher desktop Python/Tk + SQLite + adaptador isolado spotDL (MIT).
- [x] Implementar importação completa, plano incremental, downloads atômicos e recuperação.
- [x] Implementar gêneros/correções, biblioteca e exportação com manifesto e lixeira.
- [x] Implementar interface, configuração, cancelamento e diagnósticos.
- [x] Validar contratos com testes e fluxos reais possíveis neste ambiente.
- [x] Empacotar Windows, publicar código e release públicos, conferir CI.

Entrega: https://github.com/Jvprotano/spoTano/releases/tag/v1.0.0
CI de publicação: https://github.com/Jvprotano/spoTano/actions/runs/40330606186
46 testes por plataforma (Windows/Linux), worker congelado validado em CI e
novamente a partir do ZIP publicado. Hash do ZIP conferido localmente.

Decisões: nenhuma exclusão automática; prévias verificam revisão do banco. Downloads
substituem versões antigas apenas depois de validar MP3. Falhas na consulta completa
abortam o plano, sem alterar associação alguma. A exportação só gerencia spoTano/ e
preserva arquivos estranhos ou modificados pelo usuário. Não há credenciais no código.

Veja docs/RESEARCH.md para pesquisa e docs/VALIDATION.md para evidência final.
