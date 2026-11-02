# Conferência do ícone 2.0.1

Conferência local em 30/10/2026, Windows, Python 3.12.3 e PyInstaller 6.22.3.

- Arte original gerada com imagegen e salva dentro do projeto. A seleção final
  usa fundo verde opaco e nota musical com seta em marfim.
- ICO com nove resoluções: 16, 20, 24, 32, 40, 48, 64, 128 e 256 pixels.
  Quadros DIB evitam a incompatibilidade observada com quadros PNG no Tk/Windows.
- Verificação com Tk e APIs nativas do Windows: ícones pequeno/grande da janela
  principal presentes; o ícone da classe de janela muda ao aplicar a marca e é
  herdado por um novo diálogo. Os quatro PNGs carregam nas dimensões esperadas.
- Wheel Python gerado e auditado: contém a arte, o ICO e os quatro PNGs. Os
  recursos também estão incluídos no pacote Windows via PyInstaller.
- Os nove quadros ICO embutidos no executável correspondem byte a byte aos
  quadros do arquivo final `spotano/assets/spotano.ico`.
- Ruff e formatação passaram. Sem expansão da suíte de testes e sem repetição
  da suíte completa para esta alteração visual e de empacotamento.
- `scripts/smoke_frozen.py` passou no executável final: imports do SDK, FFmpeg,
  transcodificação real de um MP3 local gerado e eventos de progresso.

## Inspeção visual

A prévia isolada abriu com a versão 2.0.1. A inspeção inicial revelou o problema
do ICO com quadros PNG, corrigido usando DIB. A tentativa de captura da arte
final foi interrompida pelo Esc físico do usuário; o Computer Use foi encerrado.
Não se afirma uma conferência visual final do executável, dos atalhos ou da barra
de tarefas. A integração final foi conferida por recursos e APIs nativas.

A entrega é um ZIP portátil local. Não foi solicitado commit, push ou publicação.
Não houve alteração da biblioteca pessoal nem teste de downloads externos,
pendrive ou rádio físico nesta atualização.
