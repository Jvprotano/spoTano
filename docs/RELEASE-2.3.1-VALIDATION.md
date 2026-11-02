# spoTano 2.3.1 — análise do segundo log de 02/11/2026

Fonte: `log completo.log`, execução `20261102T181551Z-d9d8ee84`.

## Resultado observado

- 253 faixas; 249 downloads (98,42%), 4 falhas de correspondência; 1990,3s no lote.
- Conferência somente de leitura: 249/249 arquivos atuais com hash correto e perfil MP3 válido.
- Nenhuma falha de transferência registrada. Os resultados de busca não confirmam por si só a gravação correta pelo conteúdo sonoro.

| Etapa | Soma nos processos | Mediana por faixa concluída |
|---|---:|---:|
| Busca | 14,64s | 0s |
| Extração | 860,62s | 1,75s |
| Transferência | 88,87s | 0,31s |
| Conversão | 2890,26s | 10,50s |
| Espera para converter | 0,65s | 0s |

As etapas paralelas se sobrepõem. Conversão representa aproximadamente 75% da soma dessas etapas, não 75% da duração de parede. A espera quase nula não sustenta aumentar o limite de conversões. Não há comparação controlada que permita prometer redução no tempo do lote.

## Correções

- Participações `[feat. …]` agora recebem a mesma normalização de `(feat. …)`. O candidato salvo de Balada Louca passa de rejeitado a compatível. Os critérios de artista, edição e duração continuam ativos.
- Expansões da busca não reavaliam metadados idênticos. Resultados com informações diferentes (por exemplo, álbum que confirma a edição) continuam sendo avaliados. Teste controlado reduz quatro avaliações a duas, sem eliminar a informação nova.
- Cada faixa limpa candidatos rejeitados e erros de consulta anteriores, inclusive ao utilizar fonte manual ou correspondência em cache. Isso evita diagnósticos atribuídos à música errada.

As três outras pendências permanecem: Deslumbrante não indica ao vivo no pedido; Liberdade Provisória exige confirmação de 2019; Tentação exige Nopelo360. Não foi removida essa proteção. Podem ser revisadas em Biblioteca → Fonte do áudio.

A reavaliação usou os candidatos registrados, sem novas consultas ou downloads dos provedores. Não confirma download posterior de Balada Louca. Os arquivos e o catálogo pessoais foram preservados.

Evidências locais: `artifacts/log-review-2.3.1/audit.json`, `matching-replay.json` e `report.txt`.

## Validação

- Suíte completa: 250 testes aprovados em 309,68s; um aviso de depreciação do spotDL/FastAPI.
- Ruff e git diff --check aprovados.
- Executável compilado; bytecode dos módulos alterados e versão conferidos contra o fonte.
- Smoke do executável aprovado: SDK, FFmpeg, MP3 real e eventos.
- Sessão congelada aprovada: duas amostras próprias via loopback, um único processo/inicialização, conversão e progresso; 13,45s. Não mede velocidade nos provedores externos.
- Pacote portátil em dist/spoTano-2.3.1-windows-x64.zip; checksum em dist/SHA256SUMS.txt.
- Não realizada inspeção visual nem teste em rádio/pendrive físico.
