# Refinamento após o teste real — 27/10/2026

Referência: dez faixas em 115,8 s, sem falhas, com três downloads e três conversões.
O usuário comparou duas conversões e obteve aproximadamente três minutos; manter
a preferência por três. O ganho adicional deve vir de trabalho evitado e evidência
melhor, mantendo MP3 192 kbps, 44,1 kHz, estéreo e ID3v2.3.

- [ ] Identificar e evitar reinicialização do extrator de mídia a cada música;
  garantir isolamento de progresso, recuperação de falhas e fechamento da sessão.
- [ ] Corrigir homônimos na classificação: identidade externa antes de confiança
  no score da busca, cache versionado e colaboradores sem herdar o primeiro gênero.
- [ ] Acrescentar gênero de catálogo por faixa, com título/artista/versão/duração
  conferidos, cache, limite de consultas e falhas sem bloquear o áudio. Verificar
  disponibilidade real e documentar os limites de YouTube e Apple/iTunes.
- [ ] Remover IDs dos nomes exportados; preservar identidade no manifesto,
  desambiguar colisões e migrar exportações existentes com recuperação segura.
- [ ] Validar regressões, fontes reais sem baixar novas músicas, lote de 200
  amostras próprias e executável Windows; entregar pacote local atualizado.

Resultados e limitações serão registrados neste documento ao concluir.
