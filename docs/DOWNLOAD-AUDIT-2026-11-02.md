# Conferência do download de chá de casa nova

Fonte: `C:\Users\jvpro\Downloads\los completa.log`, execução
`20261031T215023Z-beeac6fe` de 31/10/2026. Análise em 02/11/2026.

## Resultado confirmado

- 200 faixas disponíveis, 186 downloads (93%), nenhuma reutilizada e 14 falhas.
- Lote: 1886,3 segundos, aproximadamente 31min26s, com dois processos de download.
- Os 186 downloads passaram pela validação original. A conferência atual encontrou
  **186/186** arquivos com SHA-256 igual ao catálogo atual e MP3 CBR 192 kbps,
  44,1 kHz, estéreo, sem capas e com ID3v2.3 quando há tags.
- As 14 falhas aconteceram na busca de correspondência. Nenhuma dessas faixas
  chegou à etapa de download do áudio nessa execução.
- Os downloads bem-sucedidos usaram uma tentativa cada; sem reinício de processo.
  Os dois mecanismos foram reutilizados ao longo de todo o lote.
- A classificação funcionou operacionalmente e organizou os arquivos em categorias.
  Esta conferência não equivale a uma revisão musical manual de cada classificação.

## Falhas e reavaliação

Foram consultados novamente os provedores, guardadas as respostas e reavaliados
os candidatos com as correções. **11 das 14** faixas passaram a ter correspondência
compatível. Encontrar correspondência não confirma o download posterior.

| Faixa | Causa identificada ou situação após correção |
|---|---|
| Hugo & Guilherme — Deslumbrante | Revisão necessária: Spotify salvo não identifica a edição; candidato próximo é ao vivo. |
| Henrique & Juliano — Desbeijar Minha Boca | Corrigida comparação de créditos separados de dupla. |
| Henrique & Juliano — Volta por Baixo | Corrigida comparação de créditos separados de dupla. |
| Henrique & Juliano — Liberdade Provisória — Ibirapuera / 2019 | Revisão necessária: candidatos próximos não confirmam o ano de 2019 solicitado. |
| Bruno & Marrone — A Dama De Vermelho — Uberlândia / 2018 | Corrigidos créditos separados e anotação de local/ano entre parênteses. |
| Gino & Geno — Ela Chorou De Amor | Corrigida comparação de créditos separados de dupla. |
| Jorge & Mateus — Amo Noite E Dia — São Paulo / 2010 | Corrigida leitura da anotação de edição entre parênteses. |
| Jorge & Mateus — De Tanto Te Querer — Goiânia / 2007 | Corrigidos créditos separados e anotação da edição. |
| Jorge & Mateus — Seu Astral — São Paulo / 2010 | Corrigida leitura da anotação de edição entre parênteses. |
| Jorge & Mateus — Pode Chorar — Goiânia / 2007 | Corrigidos créditos separados e anotação da edição. |
| Jorge & Mateus — Eu Quero Só Você | Título alternativo “Be With You” em parênteses impedia a comparação. |
| Fred & Fabrício — É Por Você Que Eu Canto / Eu Sou Desejo, Você É Paixão | Variações de títulos traduzidos do medley impediam a comparação. Continua exigindo medley completo e duração compatível. |
| Marcos & Belutti — Como Um Beijo | Reconhecidos todos os colaboradores antes do título do vídeo. |
| Mayke & Rodrigo — Tentação (Nopelo360) | Revisão necessária: candidato próximo não confirma a edição Nopelo360. |

O ano explícito continua obrigatório; covers, remixes, acústicos, gravações ao vivo
ou durações incompatíveis continuam sendo rejeitados quando não correspondem ao pedido.
As três pendências podem ser resolvidas em Biblioteca → Detalhes e ajustes → Fonte do áudio.

## Desempenho

Nas 186 faixas bem-sucedidas, o tempo agregado medido foi:

| Etapa | Soma nos processos | Mediana por faixa |
|---|---:|---:|
| Conversão | 2727,99s | 13,57s |
| Extração | 662,39s | 1,80s |
| Busca | 118,26s | 0,52s |
| Transferência | 68,74s | 0,33s |

As somas se sobrepõem entre processos e não são a duração de parede do lote.
O gargalo observado foi a conversão; aumentar downloads indiscriminadamente
não foi validado como melhoria.

Uma comparação local reconverteu a mesma faixa de 165 segundos, duas vezes por
configuração, mantendo o encoder e os parâmetros de áudio. O FFmpeg do SDK usava
log de depuração, gerando aproximadamente 882 KB de saída por conversão.

| Configuração | Tempos | Média |
|---|---|---:|
| Log original | 19,125s / 19,046s | 19,086s |
| Somente áudio e log info | 16,672s / 16,985s | 16,829s |

A redução foi de aproximadamente **11,8% nessa amostra de conversão**. O áudio
resultante das duas configurações teve SHA-256 idêntico. A saída de log caiu para
aproximadamente 8 KB. Foi aplicada a configuração `-vn -loglevel info`; limitar
threads de filtros não mostrou benefício consistente e não foi aplicado.
O ganho em uma playlist completa depende de CPU, duração, provedores e concorrência.

A busca também deixa de repetir a mesma consulta `ytsearch10` na expansão de página,
e tenta uma consulta compacta adicional quando o nome contém anotações extensas.
As opções de organização são lidas uma vez por operação, evitando abrir uma conexão
ao catálogo para cada caminho calculado durante downloads e reorganização.

## Registro e recuperação

Cada execução agora salva a fila antes dos downloads e gera:

- `events.jsonl`: eventos e fila da execução, com nomes, artistas e playlists.
- `summary.json`: resultado de cada faixa, incluindo reutilizadas, canceladas e pendentes.
- `report.txt`: relatório legível com resultados e motivos.
- `failures.csv`: somente itens não concluídos, com identidade, etapa e motivo.

O resultado do lote oferece **Ver relatório**. Os diagnósticos de busca incluem
os candidatos rejeitados e os critérios de rejeição; timeouts preservam etapa e
trecho sanitizado do log do mecanismo. Uma falha do `taskkill` agora usa encerramento
direto do processo principal e preserva o erro original, registrando a ressalva
de que o encerramento dos descendentes não foi confirmado.
O log passa a distinguir faixas **processadas**, **baixadas** e **com falha**.
A preparação de um processo novo pode usar até 120 segundos, mantendo o limite
total de 480 segundos da faixa; isso acomoda a importação lenta do SDK observada
nesta máquina sem reiniciar prematuramente o mecanismo.

O script `scripts/audit_download_run.py` abre o catálogo somente para leitura,
confere arquivos atuais e gera relatórios em outra pasta. Também reconstrói filas
interrompidas sem `summary.json`, usando os eventos completos anteriores ao encerramento.

Relatórios desta análise estão junto da execução original, na subpasta
`review-20261102/`, incluindo `audit.json`, `report.txt`, `failures.csv` e
`matching-review.csv`. O registro original foi preservado.

Uma primeira tentativa de baixar três faixas corrigidas em catálogo temporário
terminou com timeouts de preparação/extração. Evidência em
`artifacts/provider-recovery-20261102/`.

Em uma nova tentativa com um processo, **Desbeijar Minha Boca** foi encontrada
com 99,55 pontos, baixada, convertida e validada com sucesso, sem falhas. Evidência
em `artifacts/provider-recovery-20261102-single/`. O lote levou 102,5s, incluindo
a inicialização lenta; esse resultado confirma a correção funcional e não é uma
comparação de desempenho com a execução original. As outras dez correspondências
corrigidas não foram baixadas nesta validação. O catálogo e os áudios pessoais
não foram alterados pelos testes.

## Validação do código

- 55 testes de biblioteca e recuperação de playlists grandes passaram, incluindo
  retomada de 240 faixas após falhas, cancelamento e encerramento do processo.
- 16 testes de opções, 10 de auditoria/busca/relatórios, 7 de sessões de download,
  5 de integração do adaptador e 1 do novo atalho de relatório passaram.
- Ruff e `git diff --check` passaram.
- Uma execução mais ampla encontrou 9 falhas e 1 erro em testes de interface que
  esperam controles, rótulos ou cores anteriores ao layout atual; inclui também um
  erro de criação de imagem Tk. Os testes não foram declarados integralmente verdes.
  O novo botão de relatório foi exercitado separadamente e passou.
- A inspeção visual via Computer Use ficou indisponível: pipe nativo e host do
  navegador indisponíveis. Os testes Tk não substituem conferência visual.
- Alterações no código-fonte; o executável e o ZIP não foram recompilados nesta tarefa.

Referências técnicas consultadas: [opções e logs do FFmpeg](https://www.ffmpeg.org/ffmpeg.html)
e [pesquisa do ytmusicapi](https://ytmusicapi.readthedocs.io/en/stable/reference/search.html).
