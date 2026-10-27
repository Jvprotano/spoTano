# Análise da primeira execução completa — 26/10/2026

**A maior oportunidade de desempenho está na busca da gravação. A duplicação entre pastas é um defeito de gerenciamento dos arquivos. A classificação também precisa aproveitar melhor as evidências que já recebe.** A recomendação é otimizar o matching, corrigir a transição de caminhos e melhorar a classificação antes de substituir todo o mecanismo de download.

Foram analisados o log fornecido, o código atual e suas dependências instaladas, os arquivos locais correspondentes, documentação e repositórios públicos. Foram feitas reproduções isoladas e uma consulta real de metadados, sem baixar músicas. A aplicação e o catálogo real não foram alterados. Os arquivos desta pasta registram a análise; alterações que já estavam no checkout foram preservadas.

## 1. O que o log realmente mede

| Trecho | Horário | Resultado |
|---|---|---|
| Prévia da playlist maior | 17:31:09 | 200 downloads previstos |
| Tentativa da playlist maior | 17:31:11–17:31:35 | 2 executores; cancelada |
| Importação da playlist de teste | 17:35:59–17:36:19 | 10 faixas importadas |
| Prévia da playlist de teste | 17:37:58–17:37:59 | 10 downloads previstos |
| Lote de teste | 17:38:02–17:43:53 | **350,9 s: 9 downloads, 1 falha; 3 executores** |
| Janela inteira do arquivo | 17:31:09–17:43:53 | 12 min 44 s, incluindo os trechos anteriores e intervalos |

O lote de dez tentativas levou **5 min 51 s**, e não doze minutos. O fluxo chegou ao final, mas a coleção ficou incompleta: falhou **Pineapple StormTv — Poesia Acústica #2: Sobre Nós**. O log registra aproximadamente 85 s entre o início dessa faixa e a falha. Não houve timeout de 480 s nessa execução.

A vazão foi de aproximadamente 1,71 tentativas/minuto ou 1,54 arquivos concluídos/minuto. A mediana do tempo individual das nove faixas concluídas foi de 90,4 s. Tempo por faixa e tempo do lote são medidas diferentes, pois as faixas se sobrepõem.

### Tempos por faixa

| Faixa | Classificação e espera pelo resolvedor | Busca | Extração antes da transferência | Conversão até tags | Total individual | Resultado |
|---|---:|---:|---:|---:|---:|---|
| Felipe e Rodrigo — Pós | 8 s | 49 s | 9 s | 13 s | 90,4 s | Outros |
| Hugo & Guilherme — Flash - Ao Vivo | 8 s | 47 s | 10 s | 13 s | 88,4 s | Sertanejo |
| Chris Stapleton — White Horse | 2 s | 72 s | 9 s | 13 s | 104,9 s | Rock e Metal |
| Guns N' Roses — Sweet Child O' Mine | 5 s | 86 s | 9 s | 32 s | 132,7 s | Rock e Metal |
| The Drums — Money | 5 s | 45 s | 9 s | 19 s | 78,9 s | Rock e Metal |
| Jeninho — Peão Todo Tatuado | 3 s | 155 s | 9 s | 15 s | 184,2 s | Outros |
| Rincon — Não é Pressa, é Pressão | 5 s | 114 s | 9 s | 13 s | 142,1 s | Outros |
| Pineapple StormTv — Poesia Acústica #2 | 4 s | 81 s até falhar | — | — | ~85 s | Falha |
| Duda Bertelli — Ponto Fraco | 7 s | 32 s | 8 s | 10 s | 56,2 s | Outros |
| Hugo & Guilherme — Flash (Minha Mente) | 0 s | 28 s | 7 s | 7 s | 43,3 s | Sertanejo |

As etapas foram calculadas pelos horários do log, com resolução de um segundo. Os totais individuais decimais vêm das medições internas da aplicação. A primeira coluna inclui o tempo aguardando o lock compartilhado; não representa apenas a duração da API. Preparação dos processos e pequenos intervalos entre etapas não aparecem nesta tabela simplificada. A decomposição completa está em [track-timings.csv](track-timings.csv).

Nas nove faixas concluídas, a soma das durações observadas foi: busca 628 s; extração antes da transferência 79 s; conversão 135 s; classificação/espera 43 s; preparação/despacho 30 s; tags/validação 3 s; transferência observada 1 s. **Essas somas são de trabalho sobreposto dos executores, não parcelas dos 350,9 s de relógio.** A busca representa aproximadamente 68% desse trabalho; incluindo a busca da faixa que falhou, fica perto de 71%.

O primeiro e o último evento de transferência ocorrem no mesmo segundo em oito arquivos e em segundos consecutivos no outro. Isso indica transferência muito curta na resolução disponível; não permite afirmar duração zero nem medir precisamente a velocidade em MB/s.

## 2. Busca: o gargalo confirmado

O aplicativo usa spotDL 4.6.0, yt-dlp 2026.10.21, yt-dlp-ejs 0.8.0 e ytmusicapi 1.12.1 no ambiente inspecionado. O perfil pesquisa YouTube Music e, se não encontra correspondência, YouTube. A transferência já é realizada por yt-dlp: trocar spotDL por yt-dlp não troca automaticamente o componente que recebe os bytes.

O caminho mais caro encontrado é `AudioProvider.get_best_result`: quando há candidatos próximos na pontuação, o spotDL busca visualizações de cada um, sequencialmente, por meio de extração de metadados do yt-dlp. O valor `8` usado por `get_best_matches` é a **distância de pontuação em relação ao melhor resultado**, não um limite de oito candidatos. Uma reprodução determinística com doze candidatos próximos fez doze consultas. Esse comportamento também aparece no [código documentado do spotDL](https://spotdl.github.io/spotify-downloader/reference/providers/audio/base/).

### Consulta real de controle

Foi repetida apenas a pesquisa de **Hugo & Guilherme — Flash - Ao Vivo**, usando o provedor instalado e sem baixar áudio:

| Operação | Tempo |
|---|---:|
| Pesquisa de songs, limite solicitado 50 | 2,703 s |
| Pesquisa de videos, limite solicitado 50 | 1,390 s |
| Extração do candidato 1 para desempate | 8,515 s |
| Extração do candidato 2 | 5,141 s |
| Extração do candidato 3 | 7,250 s |
| Extração do candidato 4 | 7,187 s |
| Total da busca | **32,359 s** |

O desempate consumiu **28,093 s, ou 86,8%** dessa busca. As pesquisas retornaram sessenta resultados cada, apesar do limite solicitado de cinquenta. O total original de busca dessa faixa no log foi 47 s; a variação reforça que uma medição isolada não é um benchmark estável. A duração usada no controle veio do MP3 existente, e não de uma nova consulta ao Spotify. A URL selecionada foi registrada em [network-search.jsonl](network-search.jsonl); não houve validação auditiva dessa seleção.

### Como melhorar

1. **Criar uma seleção rápida por confiança.** Priorizar identidade dos artistas, título, duração, edição ao vivo/estúdio, remix/remaster, álbum quando disponível e ISRC quando já existir. Aceitar o primeiro resultado de alta confiança e margem suficiente sobre o segundo. Deixar desempates caros para casos realmente ambíguos.
2. **Limitar candidatos e paginação de forma progressiva.** Testar uma primeira página menor e ampliar apenas se não houver resultado confiável. O `limit` é exposto pelo [ytmusicapi](https://ytmusicapi.readthedocs.io/en/stable/reference/search.html). A quantidade efetivamente retornada precisa ser medida.
3. **Reduzir consultas de visualizações.** Utilizar contagens que já vierem na resposta; experimentar ranking sem consultas extras. Popularidade pode servir de desempate secundário, mas não deve superar uma edição correta por outra mais popular. Essa alteração exige conferir qualidade das correspondências.
4. **Guardar correspondências confirmadas.** Persistir Spotify ID, ID/URL canônica do vídeo, provedor, evidências da escolha e versão do matcher. Hoje o adaptador ignora o objeto Song retornado pelo SDK, que recebe `download_url`, e guarda apenas o caminho do arquivo. Não persistir URLs temporárias assinadas de mídia como se fossem permanentes; renovar a extração quando necessário.
5. **Tentar outro candidato compatível quando a extração falhar.** No fluxo atual, o fallback de busca para outro provedor não é uma recuperação automática de toda falha posterior na URL escolhida. Preservar diferenças de versão e confiança ao escolher uma alternativa.
6. **Controlar tempos por fase.** Manter o limite total como proteção, mas registrar e limitar separadamente pesquisa, candidatos, extração, transferência e conversão, com retries adequados à causa. Reduzir cegamente o timeout total pode transformar faixas lentas em falhas.

Uma adaptação concentrada no provedor de busca, dentro do processo isolado existente, permite avaliar essas estratégias sem reescrever catálogo, exportação e conversão. Cache, confirmação manual de uma URL e diagnóstico detalhado também continuam úteis se o mecanismo for trocado depois.

## 3. “Outros” e categoria específica: dois problemas distintos

### Cópias antigas no disco

Foram encontrados **três Spotify IDs em duas pastas** na biblioteca padrão:

- Gusttavo Lima — 10 Anos - Ao Vivo;
- Hugo & Guilherme — Mentirosa - Ao Vivo;
- João Bosco & Vinícius — Sorte É Ter Você (Carolinas).

São faixas da playlist maior. As nove faixas salvas no lote de teste aparecem uma vez por ID no disco inspecionado; o log também registra um único salvamento por faixa nesse lote. Portanto, **não há evidência de que os dez downloads tenham sido duplicados nessa execução**.

O defeito foi reproduzido em um catálogo temporário: baixar inicialmente em Outros, atualizar os metadados para uma categoria específica e forçar novo download deixa dois arquivos. Em `Library.apply`, o novo caminho é instalado e gravado no banco sem dar destino ao caminho antigo. A reorganização posterior só conhece o caminho novo e já não consegue recuperar o anterior. Já `Library.reorganize`, numa mudança normal de categoria, copia, confirma o novo caminho e remove a origem verificada.

Isso explica um mecanismo capaz de produzir a situação observada, mas não prova o histórico exato dos três arquivos reais. Há uma limitação adicional: o SQLite encontrado no diretório padrão tem esquema e estado anteriores ao lote, sem as dez faixas de teste cadastradas. Ele não pode ser usado para reconstruir com confiança qual arquivo era canônico na execução fornecida. Não foi restaurado nem modificado.

Para corrigir:

- Registrar a transição de caminhos antes de substituir o vínculo no catálogo; validar o novo arquivo e confirmar o banco; então encaminhar a versão antiga conhecida para a lixeira, com recuperação após interrupção.
- Na reclassificação sem mudança do áudio, mover/reorganizar o arquivo existente, sem novo download ou conversão.
- Criar uma revisão dos arquivos físicos sem vínculo e dos IDs presentes em mais de um caminho. A limpeza atual de faixas sem playlist consulta o catálogo e não encontra necessariamente cópias antigas que ficaram fora dele.
- Em arquivos antigos sem histórico confiável, apresentar os conflitos para revisão. Não apagar por título ou supor equivalência apenas porque os nomes coincidem.

Os hashes completos das três duplas diferem. Em Mentirosa e Sorte É Ter Você, o conteúdo após retirar os blocos ID3 é igual; em 10 Anos esse conteúdo difere e as durações também: aproximadamente 217,313 s contra 216,686 s. Isso não prova gravações diferentes, mas impede tratar todas as duplas como arquivos binariamente idênticos. Os detalhes estão em [local-inspection.json](local-inspection.json) e [metrics.json](metrics.json).

### Qualidade da classificação

Quatro dos nove arquivos concluídos foram para Outros. A faixa que falhou também havia recebido Outros. O destino único já é a intenção do classificador: ele retorna uma categoria por vez. A duplicação física não vem de retornar simultaneamente duas categorias.

O problema mais claro de classificação é **Chris Stapleton → Rock e Metal**. A consulta atual ao MusicBrainz retornou `country` com três votos, `bluegrass` com um, `outlaw country` com um e `southern rock` com um. O resolvedor descarta os votos e passa somente os nomes ao classificador. Como Rock e Metal é testado antes de Country e Folk, uma tag minoritária de rock vence. A resposta está em [musicbrainz-live.json](musicbrainz-live.json).

Recomendações:

1. Preservar tags com pesos, entidade identificada, fonte, data e evidência. Separar pontuação da categoria de validação da identidade do artista.
2. Escolher a categoria por evidência ponderada e especificidade, com política explícita para empates. Termos brasileiros específicos devem prevalecer sobre rótulos excessivamente amplos quando a evidência sustenta isso.
3. Preferir evidência da gravação quando disponível, usando artista como fallback. Colaborações e projetos como Pineapple exigem considerar os demais artistas, sem presumir que todas as faixas de um artista tenham o mesmo gênero.
4. Usar IDs estáveis de artista no cache quando existirem; nome normalizado sozinho pode misturar homônimos. Continuar rejeitando identidades conflitantes.
5. Versionar o cache quando mudar a taxonomia ou o formato dos pesos. O botão Reclassificar atualmente consulta o cache válido; ele não força atualização da fonte. A ausência pode persistir um dia e um resultado reconhecido, inclusive inadequado, até noventa dias.
6. Tornar a correção por artista uma opção explícita, preservando a correção específica por faixa como prioridade. Isso reduz trabalho repetitivo sem impor um único gênero a toda colaboração.
7. Ampliar o vocabulário brasileiro com exemplos revisados: agrofunk, funknejo e variações de grafia, por exemplo. A associação desses estilos híbridos a uma pasta deve ser uma política do produto, não uma suposição baseada no nome da música.

Há também uma pequena perda de desempenho: um único lock envolve cache e todas as consultas de gênero. Na primeira faixa de Hugo & Guilherme, um resultado em cache esperou aproximadamente oito segundos por outras classificações. Separar cache, deduplicação de consultas por artista e limitador por fonte evita essa espera. Não se deve simplesmente paralelizar chamadas do MusicBrainz: sua [política documenta limite médio de uma requisição por segundo por IP e uso de 503 para throttling](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting). O log contém três avisos de 503; eles não provam, isoladamente, violação desse limite.

## 4. Outras falhas e melhorias úteis

**Causa original da falha perdida.** A mensagem de Poesia Acústica afirma indisponibilidade ou bloqueio, mas é uma mensagem genérica gerada quando o SDK retorna caminho vazio. O SDK registra erros mais específicos em `errors`; o adaptador não os aproveita e o log temporário do processo é removido no encerramento. Como a faixa falhou antes do evento “Obtendo informações do áudio”, o log não comprova um bloqueio durante a transferência. Guardar erro original sanitizado, etapa, provedor e tentativas é prioridade. Distinguir nenhum resultado, resultado incompatível, rede, rate limit, extração, conversão e arquivo inválido permite recuperação correta.

**Proveniência e qualidade da gravação.** Um MP3 válido e com SHA-256 correto não prova que seja a gravação solicitada. A validação atual confere leitura, duração positiva, bitrate positivo, 44,1 kHz e estéreo; não compara duração com o Spotify nem confirma versão. Acrescentar diferença de duração, artista/canal, título/edição, score e URL ao diagnóstico. Criar revisão das correspondências ambíguas e permitir escolher uma URL compatível por faixa, além da associação de MP3 local já disponível. Não deduplicar “Flash - Ao Vivo” e “Flash (Minha Mente)” apenas por semelhança do título: têm IDs e durações diferentes.

**Tags de gênero ausentes nos MP3s.** Todos os dezessete arquivos inspecionados estão sem `TCON`, inclusive os de pastas específicas. A categoria resolvida é usada para a pasta/banco, mas não é passada para a gravação das tags do SDK; correções também apenas reorganizam caminhos. Rádios que navegam por gênero podem continuar sem essa informação. Gravar a categoria efetiva na tag, mantendo ID3v2.3; recalcular SHA-256 e a revisão após mudar os bytes para que exportações incrementais detectem a alteração.

**Perfil de áudio atendido nesta amostra.** Os dezessete arquivos locais inspecionados são MP3 CBR 192 kbps, 44,1 kHz, estéreo e ID3v2.3. Isso é evidência positiva de formato, sem comprovar compatibilidade física com o rádio. A validação poderia verificar explicitamente CBR, bitrate, versão ID3 e ausência de capa, além das condições atuais.

**Conversão tem custo real, mas secundário.** No log, as conversões das nove faixas somaram aproximadamente 135 s de trabalho sobreposto. Um controle local com 180 s de sinal sintético em Opus, mesmo conversor e perfil, levou 4,281 s sozinho e cerca de 10,1 s por arquivo com três conversões simultâneas. O conteúdo sintético e a carga atual não reproduzem as músicas nem a máquina no momento do log; o controle mostra que mais conversões simultâneas podem disputar CPU. Medir uma fila de conversão separada pode ser útil depois da busca. Trocar a saída para Opus ou M4A eliminaria parte do trabalho, mas mudaria o requisito automotivo; não é uma otimização equivalente.

**Paralelismo já funciona.** As três vagas permaneceram quase sempre ocupadas. A estimativa de ocupação, usando tempos individuais e a duração aproximada da falha, é de 95,6%; não é uso de CPU. A inicialização de 7,2–9,0 s ocorre uma vez por executor, e os demais downloads reutilizam o mecanismo. Aumentar de três para quatro executores deve ser comparado depois de reduzir consultas desnecessárias, medindo tempo, falhas e CPU. A fila atual não parece ser a causa principal da demora.

**Observabilidade.** Registrar um ID de execução, versão/build, diretório de dados, dependências, configuração, IDs das faixas, relógio monotônico por etapa, candidato selecionado, contagem de consultas, retries e resumo final estruturado. Manter na interface o progresso resumido por faixa e os avisos de espera; deixar detalhes repetitivos no diagnóstico exportável. Exibir “concluído com falhas” e ação de continuar apenas pendências ajuda a distinguir fim da fila de coleção completa.

## 5. Alternativas pesquisadas e decisão sugerida

### Download e busca

| Opção | O que resolve | Avaliação para o spoTano |
|---|---|---|
| spotDL com busca adaptada | Mantém os tipos, metadados, conversão e integrações atuais | Primeira opção para uma prova comparativa: atacar consultas extras preservando a infraestrutura existente |
| ytmusicapi + yt-dlp + FFmpeg com fluxo próprio | Controle direto sobre candidatos, cache e tempos por fase | Principal alternativa se a adaptação do spotDL exigir muitos contornos; passa ao spoTano a manutenção do matcher e das regras de recuperação |
| pytubefix | Extração/download em Python | Alternativa técnica para teste, sem evidência coletada de melhor desempenho completo nesta playlist; ainda precisa de matching e conversão. [Repositório](https://github.com/JuanBindez/pytubefix). |
| YouTube.js | Cliente da API interna InnerTube, em JavaScript | Exige integrar outro ecossistema e manter o fluxo de correspondência. Não foi encontrado benchmark comparável ao nosso lote. [Repositório](https://github.com/LuanRT/YouTube.js). |
| Biblioteca Rust `boul2gom/yt-dlp` | Usa yt-dlp para metadados, cache e transferência HTTP segmentada | Possui benchmark publicado, discutido abaixo; não resolve por si só a busca Spotify→gravação. [Repositório e medições](https://github.com/boul2gom/yt-dlp). |
| YouTube Data API | Pesquisa oficial de vídeos | Requer projeto/chave e quota de busca; não substitui o mecanismo de extração. A documentação consultada informa cem chamadas de busca por dia na quota padrão descrita. Precisa de avaliação própria para listas de duzentas músicas. [Documentação](https://developers.google.com/youtube/data/reference/rest/v3/search/list). |

O benchmark do wrapper Rust publica áudio em 192 kbps em **8,53 s com yt-dlp contra 1,26 s no perfil Balanced**, em média de dez execuções. O próprio autor informa que a comparação inclui metadados refeitos no caminho yt-dlp e metadados previamente obtidos/cacheados no wrapper. Não mede nossa pesquisa por candidatos nem nossa conversão MP3. Serve como evidência de uma estratégia de reaproveitamento; não como promessa de baixar cada música do spoTano em um segundo. [Método e resultados](https://github.com/boul2gom/yt-dlp).

No nosso log, a transferência já é curta. Mesmo uma redução forte nessa etapa teria impacto pequeno no lote se a busca continuar levando até 155 s. O `--concurrent-fragments` do [yt-dlp](https://github.com/yt-dlp/yt-dlp) atua em fragmentos de DASH/HLS, não na busca de candidatos. Acelerar essa etapa não substitui otimizar o matcher.

Manter Deno/EJS preparado também continua adequado: faz parte do [suporte atual do yt-dlp a YouTube](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Não houve evidência suficiente para atribuir o tempo histórico especificamente à execução JavaScript; é preciso instrumentá-la antes de trocar o runtime.

### Classificação

| Fonte/abordagem | Benefício | Limite e decisão |
|---|---|---|
| MusicBrainz + Wikidata | Integrações já existentes e identidades estruturadas | Aproveitar votos, IDs e evidência por gravação; manter cache e limite por fonte. Mais chamadas não criam tags ausentes. [API Wikibase](https://www.mediawiki.org/wiki/Wikibase/API). |
| Last.fm, tags de faixa e artista | Fornece tags ordenadas por contagem/popularidade | Melhor fonte complementar a experimentar; exige chave de API e validação de cobertura brasileira. Não foi validada via API nesta análise. [Faixa](https://www.last.fm/api/show/track.getTopTags), [artista](https://www.last.fm/api/show/artist.getTopTags). |
| Spotify, gênero de artista | Identidade alinhada ao catálogo de origem | A referência atual marca `genres` como depreciado. Não basear a solução nova na garantia desse campo. [Get Artist](https://developer.spotify.com/documentation/web-api/reference/get-an-artist). |
| Essentia/modelos de áudio | Classifica o conteúdo sonoro após o download | Pesquisa posterior para faixas sem evidência. Exige medir CPU, empacotamento Windows, taxonomia brasileira e licença dos pesos. [Modelos](https://essentia.upf.edu/models.html), [licenciamento](https://essentia.upf.edu/licensing_information.html). |
| AcoustID/Chromaprint | Ajuda a identificar gravações existentes | Complemento de identidade; não é um classificador de gênero isolado. [Serviço](https://acoustid.org/webservice). |

Last.fm não garante resolver todos os casos: a página consultada de Jeninho apresenta apenas a tag ampla “brazil”, e o artista aparece sem gêneros/tags no MusicBrainz. Uma terceira fonte melhora a chance de cobertura, mas não justifica adivinhar categorias. [Last.fm](https://www.last.fm/de/music/Jeninho), [MusicBrainz](https://musicbrainz.org/artist/a25bc777-276a-4a59-958f-99e04d683cc8).

Os modelos de Essentia têm taxonomias diferentes das pastas do spoTano; a lista MTG-Jamendo de 87 classes não inclui Sertanejo/Pagode como classes próprias. Os pesos pré-treinados também têm condições de distribuição específicas. Por isso, a avaliação deve começar por cobertura e classificação correta em música brasileira, antes de investir no empacotamento.

## 6. Ordem de execução proposta

| Prioridade | Entrega | Evidência de aceitação |
|---|---|---|
| 1 | Corrigir transição de caminhos e preservar causa original das falhas | Forçar download mudando categoria deixa um arquivo ativo; versão anterior recuperável; interrupção não perde áudio; erro identifica a etapa real |
| 2 | Instrumentar e adaptar o matcher | Comparar mesmas faixas/versões; reduzir consultas extras sem aceitar gravações erradas; persistir correspondências confirmadas e permitir revisão |
| 3 | Ponderar classificação, versionar cache e sincronizar tags | Country com evidência forte deixa de perder por ordem fixa; override preservado; uma pasta ativa; TCON e hash/exportação coerentes |
| 4 | Testar Last.fm como complemento | Medir quantas ausências resolve corretamente e latência adicionada, com chave configurada; preservar desconhecido quando não houver evidência |
| 5 | Comparar 2/3/4 executores e conversão separada | Menor tempo total com taxa de sucesso e qualidade pelo menos equivalentes |
| 6 | Avaliar substituição do spotDL ou modelo local | Só avançar se a alternativa vencer no mesmo conjunto e justificar custo de manutenção/distribuição |

### Experimento comparativo necessário

Usar as mesmas dez faixas, acrescidas de um conjunto revisado com música brasileira, colaborações, homônimos, ao vivo/estúdio, remasters e casos sem resultado. Congelar os metadados de entrada e revisar a gravação esperada. Alternar ordem das estratégias para reduzir efeito de horário/rede; executar pelo menos três repetições quando o provedor permitir.

Medir separadamente: preparação fria, busca sem cache de correspondência, repetição com cache, extração/transferência, conversão e reutilização de arquivo local. Relatar mediana, dispersão, casos lentos, sucesso, gravações corretas e categorias corretas entre as atribuídas. Percentis de uma amostra de dez não devem ser apresentados como estimativa robusta de produção. A taxa de Outros deve ser acompanhada junto com precisão: reduzi-la por palpites não é progresso.

Como meta inicial de engenharia, buscar uma redução relevante do lote de 350,9 s, principalmente nos casos acima de cem segundos, sem regredir identidade/edição e confiabilidade. Não há medição suficiente para prometer agora dois minutos ou um valor fixo por música. Uma extrapolação puramente linear do lote atual daria cerca de 117 min para duzentas tentativas, mas repetição de artistas, cache, limites e falhas podem mudar bastante esse resultado; não é uma previsão.

## 7. Evidência e limites da análise

- Entrada: `C:/Users/jvpro/Downloads/log 10 musicas.log`; lote nas linhas 249–625.
- Código: checkout em `acc04fab86bf330422694d017a5344cb8113393d` com alterações locais já existentes. O arquivo PyInstaller `build/spoTano/PYZ-00.pyz` foi comparado ao código atual dos módulos principais, sem divergências nos oito módulos verificados. Isso não identifica o executável exato que gerou o log do usuário.
- [metrics.json](metrics.json): eventos por faixa, agregados, leitura do catálogo e IDs duplicados.
- [track-timings.csv](track-timings.csv): decomposição por faixa; tempos inteiros aproximados por etapa.
- [probes.json](probes.json): reprodução temporária da duplicação, precedência das categorias e consultas a doze candidatos.
- [network-search.jsonl](network-search.jsonl): controle real de pesquisa/metadados, sem mídia.
- [musicbrainz-live.json](musicbrainz-live.json): resposta atual com votos das tags de Chris Stapleton.
- [local-inspection.json](local-inspection.json): perfil, duração, tags e hashes do conteúdo sem ID3 dos arquivos existentes.
- [ffmpeg-synthetic.json](ffmpeg-synthetic.json): conversão de sinal sintético isolada e em três processos simultâneos.

Não foram baixadas novas músicas, removidos duplicados, modificados catálogo/configurações reais, feitas novas exportações ou implementadas correções no produto. Não houve avaliação auditiva das nove correspondências, teste físico no rádio, benchmark completo de motores alternativos nem teste da API Last.fm. As reproduções confirmam defeitos e custos específicos; não substituem a validação completa depois da implementação.
