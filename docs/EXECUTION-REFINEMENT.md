# Refinamento após o teste real — 27/10/2026

Referência: dez faixas em 115,8 s, sem falhas, com três downloads e três conversões.
O usuário comparou duas conversões e obteve aproximadamente três minutos; manter
a preferência por três. O ganho adicional deve vir de trabalho evitado e evidência
melhor, mantendo MP3 192 kbps, 44,1 kHz, estéreo e ID3v2.3.

- [x] Identificar e evitar reinicialização do extrator de mídia a cada música;
  garantir isolamento de progresso, recuperação de falhas e fechamento da sessão.
- [x] Corrigir homônimos na classificação: identidade externa antes de confiança
  no score da busca, cache versionado e colaboradores sem herdar o primeiro gênero.
- [x] Acrescentar gênero de catálogo por faixa, com título/artista/versão/duração
  conferidos, cache, limite de consultas e falhas sem bloquear o áudio. Verificar
  disponibilidade real e documentar os limites de YouTube, Apple/iTunes e Deezer.
- [x] Remover IDs dos nomes exportados; preservar identidade no manifesto,
  desambiguar colisões e migrar exportações existentes com recuperação segura.
- [x] Validar regressões e fontes reais. Entrega final focada no código: o usuário
  dispensou novas rodadas de testes, versão e executável para integrar outras mudanças.

Resultados e limitações estão registrados abaixo.

## Implementação

Alterações de código para integração com outras mudanças. Os pacotes locais
experimentais não constituem uma entrega de versão. Nenhuma publicação remota
ou alteração do catálogo real faz parte desta entrega.

O SDK spotDL 4.6.0 construía um `AudioProvider`/`YoutubeDL` para cada gravação,
apesar de o processo já ser persistente. O adaptador agora mantém um por processo,
substitui o callback de progresso a cada tentativa e fecha o cliente ao encerrar.
As URLs temporárias de áudio continuam sendo obtidas para cada download. As
consultas de gêneros também mantêm sessões HTTP por thread, fechadas ao concluir.
Se o processo encerra sem resposta, a mesma faixa recebe uma única tentativa em
um processo novo, dentro do limite total de tempo. Cancelamentos, timeouts e erros
normais de uma faixa não acionam essa recuperação. O código de saída e o número
de reinícios ficam nas métricas; falha repetida permanece visível.
Cada reinício recebe uma pasta temporária própria para que um processo nativo
remanescente não possa escrever sobre o trabalho da nova tentativa.

A classificação usa, nesta ordem, correções manuais/metadados, evidência recente
da mesma gravação, iTunes, Deezer e fontes de artista. O iTunes fornece gênero por
faixa; o Deezer fornece gêneros do álbum da gravação conferida. Título, artista,
edição e duração precisam ser compatíveis. No Deezer, apenas o álbum do candidato
validado é consultado; não há uma requisição de detalhe para cada resultado.
Rótulos amplos como Pop e Latina ficam como último recurso. Colaboradores são
consultados em número limitado e divergências entre categorias específicas não
são decididas pela ordem dos créditos. Correções por faixa e por artista têm
prioridade sobre consultas automáticas.

Busca de artista com nomes iguais considera também candidatos de score menor.
O vínculo do Spotify no MusicBrainz desambigua esses casos; nomes curtos exigem
identidade externa. Cache anterior de gênero é invalidado pela versão 4. Ao
atualizar playlists selecionadas, categorias antigas são revistas sem substituir
áudios válidos. Alterar categoria atualiza tags, hash e caminho de forma recuperável.

O iTunes é limitado a aproximadamente 20 consultas/minuto; o adaptador espaça
requisições em 3,1 s e reaproveita resultados de outras faixas do mesmo artista.
Deezer, MusicBrainz e Wikidata têm espaçamento de 1,1 s. Há orçamento de 20 s por
classificação, incluindo espera por limites e locks. Limites de conexão/leitura,
cancelamento e suspensão de fonte após falhas consecutivas impedem cascatas de
consultas. DNS, sistema operacional e uma requisição em andamento podem exceder
um pouco esse orçamento; ele não representa um timeout rígido de processo.
Falhas não são gravadas como ausência definitiva de gênero. Evidências negativas
expiram em um dia; positivas em 90 dias. Catálogos/álbuns têm cache próprio.

A exportação deriva nomes dos metadados e mantém a pasta de organização. A
identidade fica no manifesto. Colisões são tratadas após conversão ASCII,
truncamento e comparação sem diferenciar maiúsculas. Uma exportação anterior é
migrada pela prévia normal: novos nomes são copiados/verificados antes de guardar
os antigos conhecidos na lixeira. Arquivos desconhecidos/alterados são protegidos.

## Fontes verificadas

- [Apple Search API](https://performance-partners.apple.com/search-api): campo de
  gênero e duração, resultados limitados, cache e aproximadamente 20 chamadas/min.
  [Exemplo de resposta](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/UnderstandingSearchResults.html).
- [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API): relações de URL
  e consulta de tags da identidade associada. Score de busca não comprova identidade.
- [YouTube Videos](https://developers.google.com/youtube/v3/docs/videos): categoria
  do vídeo e tópicos musicais são evidências gerais; não cobrem bem as categorias
  brasileiras específicas necessárias aqui. Tags livres não são tomadas como gênero.
- [Deezer Album](https://developers.deezer.com/api/album): portal atualmente pede
  login. A disponibilidade foi verificada diretamente nos endpoints públicos de
  busca/álbum, sem credenciais e sem acessar áudio ou prévias.

## Evidência e limites de desempenho

Consulta real confirmou `Pós (Ao Vivo)` / Felipe e Rodrigo como Sertanejo no
iTunes e a gravação de 471 s de `Poesia Acústica #2: Sobre Nós` como Rap/Hip Hop
no Deezer (álbum 584929072, gravação 2794725042). O catálogo Apple também devolveu
Pop para Peão Todo Tatuado; o cruzamento com Mariana Fagundes manteve Sertanejo.
Esses resultados motivaram o tratamento separado de rótulos amplos.

Uma sondagem de seis extrações de metadados do YouTube não isolou ganho de rede:
os tempos variaram entre as rodadas. A reutilização elimina construções repetidas;
não há porcentagem de ganho adicional comprovada para músicas reais. O lote de
200 amostras próprias verifica mecanismo, concorrência e integridade, sem prever
o tempo de uma playlist real. A configuração recomendada para a próxima comparação
é a mesma do melhor teste do usuário: três downloads e três conversões.

## Validação do código

158 testes distintos validados: suíte de 154 testes e uma rodada focada de 36,
incluindo quatro regressões adicionais. Os novos casos cobrem identificação de
gravação, dados inválidos, cache compartilhado/reinício, homônimos com score
enganoso, falhas sem cache negativo, limite de consultas, divergência de
colaboradores, gêneros amplos, revisão sem download, mudança de configuração e
remoção de correção manual. Exportação cobre migração de manifesto antigo,
retomada após interrupção e colisões de caixa, acentos e truncamento nos três
layouts. A integração real com SDK/FFmpeg confere reutilização de cliente e
isolamento dos callbacks de progresso entre faixas. Ruff e diff verificados.
Interrupções provocadas com códigos 42/43 validam recuperação da mesma faixa,
reutilização na faixa seguinte e parada após uma única nova tentativa.

O ensaio de 200 amostras encontrou uma interrupção de processo (199 concluídas).
Isso levou à recuperação automática e ao isolamento de temporários, validados
nos testes focados. O lote completo não foi repetido após essa correção; o usuário
dispensou testes e empacotamento adicionais para seguir com a integração do código.
