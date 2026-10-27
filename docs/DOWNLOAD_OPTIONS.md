# Opções de download e evidência dos tempos

O contrato `settings.download_options` contém três booleanos independentes:
`categories`, `artists`, `metadata`. Todos começam desativados, também na primeira
migração de um catálogo antigo. As escolhas seguintes persistem sem reset.

Sem categorias, `GenreResolver.resolve` não participa do download ou da
reorganização. `classified` diferencia uma classificação antiga de uma faixa
baixada sem essa etapa; ativar categorias depois pode classificar sem novo
download. Um resultado `Outros` não dispara nova consulta em cada reorganização.

O spotDL 4.6.0 não oferece uma configuração para desativar todas as tags. No
processo isolado, o adaptador suspende sua função `embed_metadata` durante o
download e restaura a função em `finally`. O Library controla as tags para ambos
os provedores (local/remoto). FFmpeg descarta metadados herdados; Mutagen remove
ID3 quando a opção está desativada. Com a opção ativa, escreve ID3v2.3 sem capa ou
consulta remota adicional. As mudanças de tags em arquivos existentes usam
staging, validação, backup, substituição e novo SHA-256.

## Estimativas fixas

Por decisão do usuário, as referências ficam em `OPTION_COSTS`, no código de
`spotano/options.py`. A aplicação não consulta logs ou histórico para calcular
essas estimativas e não grava novas amostras `option_timing`. Registros antigos
permanecem preservados, sem participar da exibição.

- **Categoria: ~8 s/música.** O log fornecido em 27/10/2026 contém dez faixas.
  Os intervalos aproximados de classificação foram 6, 10, 8, 5, 3, 7, 11, 31, 3 e
  0 segundos: cerca de 84 segundos de trabalho de classificação, ou 8,4 s/faixa,
  arredondados para 8 s. Incluem consultas a MusicBrainz/Wikidata, tentativas após
  HTTP 503 e uma faixa com vários artistas. A última reutiliza o artista já
  consultado. São referências de uma execução anterior do classificador, não um
  benchmark do código atual. Como as consultas ocorriam em paralelo com áudio e
  outras faixas, 84 s não representa a economia na duração total do lote.
- **Artistas: menos de 1 s/música.** Estimativa conservadora para criar pastas
  usando o artista já conhecido. No log enviado, a validação e a gravação local
  geralmente aparecem no mesmo segundo, ou no seguinte. A criação de pastas não
  foi medida separadamente; o valor indica custo baixo, não uma média medida.
- **Metadados: ~0,1 s/música.** Referência dos logs já analisados: 29 faixas
  concluídas em cinco sessões, com média de `tags_s` de 0,118966 s, arredondada para
  um décimo de segundo. O novo log também mostra tags e validação no mesmo segundo.

Esses valores servem apenas para dar uma noção do custo de habilitar as opções.
Não incluem download, conversão, verificação de integridade ou cópia para o
destino e não são somados para prometer uma duração total. Cache, rede,
quantidade de artistas e hardware podem mudar o custo real. Nenhum dado pessoal
do log foi incorporado ao código.

## Validação

Os testes cobrem todas as oito combinações, migração/persistência, ausência de
classificação no modo simples, exportação plana e conflitos, mudanças de tags
sem novo download e preservação de quadros de áudio. A integração com FFmpeg usa
áudio gerado localmente e verifica um MP3 real passando de simples a todas as
opções e de volta ao simples. A compatibilidade em rádio físico e a velocidade
do provedor em novos downloads não são estabelecidas por esses testes.

Em 27/10/2026, a suíte final passou com **61 testes** (um aviso de depreciação do
FastAPI usado pelo spotDL). Ruff lint, formato e `git diff --check` passaram.
A revisão na interface nativa em 920 × 640 confirmou o modo simples inicial,
o resumo das escolhas, as médias ao lado das opções e os botões Marcar tudo,
Desmarcar tudo e Concluir. A integração isolada com MP3 real passou em 16,93 s;
o caminho local usa FFmpeg do sistema quando disponível, com fallback para a
instalação gerenciada pelo spotDL. Não foi gerado um novo executável nesta tarefa.

Após substituir as médias dinâmicas pelas estimativas fixas, os **43 testes** de
opções, biblioteca e integração passaram novamente. A regressão de estimativas
bloqueia acesso ao histórico e a arquivos de log durante sua exibição. Ruff lint,
formatação dos arquivos alterados e `git diff --check` também passaram.
