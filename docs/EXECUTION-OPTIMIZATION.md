# Plano de execução — desempenho e qualidade — 26/10/2026

Objetivo: reduzir o primeiro download de playlists de 200 músicas, mantendo a identidade da gravação, o perfil MP3 automotivo e a recuperação segura. Referência: lote de 10 tentativas em 350,9 s, 9 sucessos e uma falha. A busca de candidatos é o primeiro alvo.

## Etapas e aceitação

- [x] 1. Busca adaptada: primeiras páginas pequenas, ranking por artista/título/duração/edição, nenhuma extração apenas para obter visualizações, expansão limitada e candidatos alternativos. Rejeitar ambiguidades; permitir URL escolhida por faixa.
- [x] 2. Cache persistente de correspondências: identidade e versão do matcher, URL canônica e evidência, invalidação de cache falho e preservação de escolha manual. Sem segunda consulta Spotify por faixa.
- [x] 3. Execução e diagnóstico: preparação reutilizada, limites por fase, erros originais sanitizados, métricas JSONL persistentes por execução, resumo comparável e fila limitada. Classificação pode sobrepor a busca; conversões com limite próprio.
- [x] 4. Integridade dos arquivos: transições registradas e recuperáveis, uma cópia ativa por faixa ao trocar categoria, revisão de cópias físicas antigas e lixeira com prévia.
- [x] 5. Gêneros: votos/especificidade, evidências por gravação quando disponíveis, colaboradores, IDs estáveis, cache versionado, consulta por artista deduplicada e limite por fonte. Last.fm opcional com chave, sem dependência dele no fluxo padrão. Correção por artista explícita e prioridade da faixa.
- [x] 6. MP3 e interface: categoria em TCON/ID3v2.3, hash e exportação coerentes, validação de perfil/duração, seleção de URL e detalhes, recuperação de falhas, acesso às métricas e revisão de duplicatas.
- [x] 7. Validação: regressões de matching, cache, cancelamento, transições/interrupções e tags; lote sintético de 200 faixas com 2/3/4 executores; pesquisa real comparável sem novas músicas; fluxo GUI e worker empacotado.
- [x] 8. Entrega: documentação de comparação, evidências e pacote Windows local atualizado para o usuário repetir as 10 faixas e depois as 200.

## Decisões

Manter spotDL 4.6.0, yt-dlp e FFmpeg. Não trocar o formato para obter ganho artificial de velocidade. Não baixar novamente para corrigir categoria. Não eliminar duplicatas desconhecidas automaticamente. Last.fm é complemento configurável; modelos locais e motores alternativos só justificam adoção se a adaptação atual não atender aos testes. Benchmarks sintéticos comprovam fila e integridade, não tempo de rede para 200 músicas. O resultado real do próximo lote do usuário continua sendo a medida final de produção.

## Evidência final

Implementação entregue na versão 1.1.0. Busca real de nove faixas: 0,344–2,078 s
por faixa, uma consulta e nenhuma extração de visualizações. Referência histórica
da mesma amostra: 28–155 s de busca. A comparação não inclui download completo.

129 testes distintos validados (suíte principal de 126 mais três novas regressões,
incluídas em uma execução focada de 33 testes). Ruff e diff sem erros. Inspeção
visual da interface Windows em 1000×760, em catálogo separado.

Lotes sintéticos com duzentas faixas passaram com 2/3/4 executores, retomada somente
da falha e reutilização integral. O executável Windows passou também por duzentas
amostras geradas com SDK/FFmpeg reais e quatro processos persistentes: 200/200,
sem falhas, todos os perfis e hashes conferidos, em 169 s. Isso não é uma previsão
do tempo de duzentas músicas reais. O teste do usuário continua medindo rede e
gravações reais, inclusive a faixa que falhou no primeiro lote.

Pacote: `dist/spoTano-1.1.0-windows-x64.zip`. Código empacotado comparado ao fonte
de quatorze módulos. Detalhes em [OPTIMIZATION-VALIDATION.md](OPTIMIZATION-VALIDATION.md).

O fluxo principal continua sem chave ou assinatura. Last.fm é complemento
configurável e teve o contrato validado em testes; o uso real requer uma chave.
Não houve adoção de outro motor ou modelo local, pois o gargalo identificado foi
removido mantendo o mecanismo atual. Nenhuma música real nova foi baixada durante
a validação e o catálogo real do usuário não foi alterado.
