# Validação das otimizações 1.1.0 — 26/10/2026

## Busca com metadados reais

Metadados de nove faixas do teste foram recuperados do Spotify para validar
nome, artistas e duração de referência. A nova busca encontrou as nove em uma
consulta por faixa, sem extrair vídeos para contar visualizações.

| Faixa | Busca no log original | Busca otimizada | Diferença de duração do candidato |
|---|---:|---:|---:|
| Pós - Ao Vivo | 49 s | 2,078 s | 1 s |
| Flash - Ao Vivo | 47 s | 0,500 s | 1 s |
| White Horse | 72 s | 0,515 s | 1 s |
| Sweet Child O' Mine | 86 s | 0,609 s | 1 s |
| Money | 45 s | 0,500 s | 1 s |
| Peão Todo Tatuado | 155 s | 0,437 s | 1 s |
| Não é Pressa, é Pressão | 114 s | 0,454 s | 0 s |
| Ponto Fraco - Ao Vivo | 32 s | 0,484 s | 1 s |
| Flash (Minha Mente) | 28 s | 0,344 s | 1 s |

Mediana observada: 49 s na amostra histórica e 0,500 s na nova pesquisa. São
consultas feitas em momentos diferentes, com seleção e referência de duração
agora verificadas; não é um ensaio controlado de download completo. Não houve
download de músicas nem validação auditiva nesta pesquisa. A faixa que falhou
originalmente não tinha seu ID no caminho salvo do log e ficou fora desta medição.

## Catálogo, fila e recuperação em 200 faixas

`scripts/benchmark_pipeline.py` executou três catálogos temporários com duzentas
faixas, uma transferência simulada com falha, retomada e reutilização integral.
Todos terminaram com duzentos arquivos, nenhum journal pendente e SQLite íntegro.

| Executores | Primeiro lote sintético | Downloads na retomada | Reutilização seguinte |
|---|---:|---:|---:|
| 2 | 20,969 s | 1 | 200 |
| 3 | 19,828 s | 1 | 200 |
| 4 | 17,578 s | 1 | 200 |

A rede e o áudio deste benchmark são simulados. Ele mede a orquestração e o
gerenciamento de arquivos; não é previsão de tempo de YouTube para duzentas músicas.

## Regressões e interface

A suíte principal passou com 126 testes. As regressões finais de progresso e
otimização passaram com 33 testes, incluindo três novos casos não presentes na
execução principal: 129 testes distintos validados. Existe um aviso de depreciação
do FastAPI no import upstream do spotDL, sem falha de teste.

Cobertura inclui rejeição de gravações/edições incompatíveis, cache e invalidação,
prioridade das escolhas manuais, consultas de artista deduplicadas, fontes sem
chave, tratamento de erros e causa original, duração/perfil MP3, alterações de
tags/hashes/exportação, arquivos externos protegidos, journal interrompido antes
da substituição, depois da instalação e depois do commit, cancelamento e IPC.

Os testes Tk cobrem seleção da fonte com download de fixture, revisão de cópias,
configuração, cache e rolagem na janela mínima. Também foram inspecionadas na
interface Windows real, em catálogo isolado, as abas Biblioteca/Configurações e
o diálogo Fonte do áudio, a 1000×760.

Um worker de fonte processou duas amostras geradas em loopback, reutilizando o
mesmo processo, com conversão real, progresso e ID3v2.3. Outro controle executou
trinta faixas de áudio gerado com quatro processos do SDK, sem falhas e com todos
os perfis/hashes verificados. A preparação do pacote foi comparada com o código
atual de quatorze módulos, incluindo busca, áudio, journal e métricas.

## Executável Windows com 200 áudios gerados

O executável 1.1.0 processou duzentas amostras geradas de um segundo, recebidas
somente por loopback, com quatro workers persistentes e duas vagas de conversão.
Resultado: **200 downloads, zero falhas, 200 perfis/hashes verificados e 200 arquivos
reutilizáveis na prévia seguinte**, em 169,0 s incluindo preparação e verificações.
Todos os processos terminaram ao encerrar o lote. Nenhuma consulta de visualizações.

Tempos somados dos workers: preparação 48,609 s; extração 376,932 s; transferência
4,520 s; fila de conversão 3,497 s; conversão 114,356 s; tags 9,052 s. São tempos
sobrepostos, não parcelas dos 169 s. A amostra de um segundo e a rede local tornam
este um teste de distribuição/escala/integridade, não de velocidade no YouTube.

Pacote local: `dist/spoTano-1.1.0-windows-x64.zip`; executável em
`dist/spoTano/spoTano.exe`; checksum em `dist/SHA256SUMS.txt`.
Os quatorze módulos do arquivo PyInstaller foram comparados ao código atual,
sem divergências. O pacote não inclui as pastas de evidência pessoal da análise.

## Como repetir o teste do usuário

1. Extraia a pasta inteira do ZIP 1.1.0 e abra seu `spoTano.exe`.
2. Use três downloads e duas conversões simultâneas para a comparação inicial.
3. Execute as mesmas dez músicas. Compare o lote completo, as falhas e a duração
   das gravações, além do tempo da busca. Depois avance para a playlist de duzentas.
4. Abra Configurações → Abrir métricas das execuções. Guarde `summary.json`,
   `events.jsonl` e, se desejar, o log textual visível.
5. Distinga primeiro download, reexecução com cache de correspondências e simples
   reutilização de MP3. Limpar o log não limpa cache. Há uma ação específica para
   limpar correspondências sem apagar músicas ou escolhas manuais.

Para isolar completamente o catálogo, o executável aceita `--data-dir` com uma
pasta nova. Não é necessário apagar o catálogo anterior para fazer essa comparação.

Comparação de execuções estruturadas:

```powershell
.venv\Scripts\python scripts\compare_runs.py caminho\primeira-execucao caminho\segunda-execucao
```

O script separa duração de relógio, tempos somados dos executores, cache, consultas,
sucessos e falhas. P95 só é calculado com pelo menos vinte faixas concluídas.
Last.fm foi validado pelo contrato em testes; a consulta real depende de uma
chave configurada. Compatibilidade física com rádio e tempo real para duzentas
músicas continuam dependendo do teste com a biblioteca do usuário.
