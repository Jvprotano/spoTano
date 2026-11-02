# spoTano 2.4.0 — conversão e recuperação de correspondências

## Conversão: alternativas e resultado

Máquina: Intel Core i3-1005G1, 2 núcleos / 4 threads; Windows 11; FFmpeg 8.0.1.
Comparação com entradas Opus 48 kHz preparadas a partir de três amostras locais,
de aproximadamente 176, 183 e 156 segundos. Nenhum arquivo pessoal foi alterado.
Dois processos de conversão simultâneos; duas rodadas com ordem invertida.
A preparação das entradas fica fora da medição; conversão, remux e validação ficam dentro.

| Caminho | Rodada 1 | Rodada 2 | Média |
|---|---:|---:|---:|
| FFmpeg + LAME atual | 14,866s | 15,355s | 15,111s |
| FFmpeg + MP3 Windows + remux | 8,579s | 9,954s | 9,267s |

**Redução média de 38,7% no tempo de conversão** (rodadas: 42,3% e 35,2%).
Os seis resultados Windows usaram efetivamente `mp3_mf`, sem fallback, e passaram
na validação de MP3 CBR 192 kbps, 44,1 kHz, estéreo. A duração divergiu no máximo
26 ms do resultado LAME correspondente.

Na triagem de trechos de 60 segundos, LAME com `compression_level=5` reduziu
moderadamente o tempo, enquanto fre:ac 1.1.7 com SuperFast LAME / 2 threads levou
2,44s contra 1,79s do FFmpeg/LAME na mesma amostra. Não foram adotados.
Um ajuste anterior de threads teve resultado inconsistente e também foi descartado.

O MP3 nativo inicial continha contagens de frames incorretas no cabeçalho Xing/Info:
um áudio de 60s aparecia como 16,9s no Mutagen. O novo fluxo sempre faz uma segunda
passagem `-c:a copy`, que reorganiza os frames e reconstrói o cabeçalho **sem recodificar**.
Só instala o arquivo depois dessa passagem e da validação do perfil.

## Impacto estimado e qualidade

No log de 253 faixas, conversão respondeu por aproximadamente 75% da soma dos tempos
das etapas. Aplicando a redução medida: `1990,3 × (1 − 0,75 × 0,387) ≈ 1413s`.
Estimativa central: cerca de 23min33s, ou aproximadamente 9min37s a menos.
Uma faixa prática estimada é **23–25 minutos**, contra os 33min10s observados.
Não é um intervalo estatístico nem medição de uma nova playlist completa: assume
perfil semelhante de faixas, carga da máquina e paralelismo. Rede e CPU podem mudar o resultado.

O encoder Windows mantém o formato, mas não produz áudio idêntico ao LAME.
Não foi feita comparação auditiva cega nem demonstrada equivalência perceptiva.
Uma comparação auxiliar de sinal, reamostrada e alinhada em mono/16 kHz, encontrou
SNR de 18,7–19,7 dB para Windows e 27,3–27,5 dB para LAME. Essa medida não é uma
nota de qualidade perceptiva e é sensível ao alinhamento e aos algoritmos.
O modo Tradicional permanece selecionável para quem prefere manter o encoder anterior.

## Implementação

- Rápida · Windows é o padrão; Tradicional · LAME está em Configurações → Desempenho.
- Sem nova dependência de execução: usa o FFmpeg existente e o encoder do Windows.
- Se o encoder não existir, a conversão falhar ou o MP3 não passar na validação,
  repete a conversão a partir da mesma entrada com LAME, sem novo download.
  O processo deixa de tentar o encoder que falhou nas faixas seguintes da sessão.
- Saída nativa e remux ficam em pasta temporária; o destino só recebe resultado validado.
- Downloads e importações locais respeitam a escolha. Arquivos anteriores não são reconvertidos.
- Métricas registram encoder real, fallback e tempo de remux.
- A calibração copia e compara o encoder escolhido; relatórios com outra configuração
  não podem ser aplicados como se medissem o mesmo trabalho.

## Três falhas restantes: investigação concluída

O adaptador de playlists devolve álbum e ISRC vazios. A consulta completa confirmou
que Deslumbrante também não identifica a edição no título/álbum do single Spotify.
Ausência de edição era tratada como uma indicação explícita de estúdio.

- **Deslumbrante:** candidato do catálogo verificado, mesmo artista/título e apenas
  1s de diferença. Ao vivo pode ser inferido somente com identidade quase exata,
  fonte verificada e duração próxima; indicação explícita de estúdio continua bloqueando.
- **Liberdade Provisória:** o vídeo do canal verificado confirma Ibirapuera, mas não
  informa o ano. Ano ausente passa a exigir local, identidade e duração próximos;
  ano explicitamente diferente continua sendo rejeitado.
- **Tentação (Nopelo360):** o YouTube Music retorna título/créditos incompletos para
  o mesmo vídeo cujo título no YouTube identifica os participantes e No Pelo 360.
  A comparação reconhece o projeto com espaços e os créditos de participação.
  Candidato de outro projeto continua bloqueado.

As três faixas foram buscadas, baixadas, convertidas e validadas em pasta isolada,
sem URLs escolhidas manualmente, em 18,97s, 17,61s e 14,74s respectivamente antes
da troca de encoder. Isso confirma recuperação funcional, não identidade por
comparação auditiva. Evidências de inferência ficam no log e no diagnóstico.

A otimização de buscas da 2.3.1 foi medida separadamente: 61,7ms → 29,2ms numa
reprodução de três buscas com candidatos repetidos. Ganho de apenas 32,5ms nessa
amostra; expectativa inferior a 1s no lote original. Não explica o ganho de conversão.

## Validação proporcional

- 11 testes direcionados de correspondência aprovados.
- 5 cenários essenciais de fallback, proteção do destino, escolha de encoder no Tk,
  isolamento da calibração e importação/conversão/exportação real aprovados.
- Não repetida a suíte completa. Sem inspeção visual ou teste em rádio físico.
- Benchmark reproduzível: `scripts/benchmark_conversion.py`.
- Evidências locais em `artifacts/conversion-research/` e `artifacts/deep-review/`.

## Referências técnicas

- [Microsoft: encoder MP3 e formatos suportados](https://learn.microsoft.com/en-us/windows/win32/medfound/mp3-audio-encoder).
- [FFmpeg: cabeçalho e muxer MP3](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/mp3enc.c).
- [fre:ac: funcionamento do SuperFast LAME](https://www.freac.org/latest-news-mainmenu-2/14-freac/287-superfastlame).
- [FFmpeg: parâmetros do LAME](https://ffmpeg.org/ffmpeg-codecs.html).
