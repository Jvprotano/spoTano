# Conferência da interface 2.0.0

Conferência em 30/10/2026, Windows, Python/Tkinter, com catálogo temporário e sem
alterar a biblioteca pessoal. Sem expansão da suíte unitária.

## Evidência atual

- Inspeção visual das quatro áreas na janela mínima de 1000×760: navegação lateral,
  tabelas, ações principais e configuração por seções.
- Playlists com estado vazio, seleção e duas playlists preenchidas; Biblioteca
  com faixas pendentes, falha, nomes extensos, busca e filtro por estado.
- Atividade expandida mantém as ações de download acessíveis. Etapa, contagens e
  cancelamento permanecem fora da área recolhível. A barra ociosa não indica trabalho.
- Conferência prática isolada exercitou importação em segundo plano, gravação no
  catálogo, atualização da seleção/Biblioteca, busca sem resultados, filtros,
  correção de categoria e persistência das opções de download.
- Diálogos de importação (620×274), ações avançadas (620×477), ajustes de faixa
  (620×519), grupos de exportação (660×460), prévia e resultado cabem no conteúdo.
- Diálogo de faixa com título longo conferido em 620×583; fonte do áudio em 820×550
  e histórico com rolagem em 820×530.
- Atalho Ctrl+2 conferido na janela real; foco e controles ttk mantidos.
- Ruff e compilação Python conferidos. Não foi executada a suíte completa.

## Pacote Windows

- Executável gerado por PyInstaller 6.22.3 / Python 3.12.3, com saída em
  `dist/spoTano/spoTano.exe` e pacote `dist/spoTano-2.0.0-windows-x64.zip`.
- Código embutido de `spotano`, `gui`, `ui`, `views` e `exporter` comparado ao código
  atual por bytecode: corresponde à versão 2.0.0. Executável distribuído idêntico
  ao verificado no diretório de build. Inventário de dependências registra 2.0.0.
- Worker do executável passou: imports do SDK, FFmpeg, transcodificação real de um
  MP3 local gerado e eventos de progresso (`scripts/smoke_frozen.py`).
- Abertura do executável com catálogo isolado confirmada pelo processo responsivo
  e título da janela `spoTano · Sua música, com você`. A inspeção visual específica
  do executável foi interrompida pelo Esc físico do usuário; não foi retomada.
  A conferência visual descrita acima ocorreu na aplicação em código-fonte.
- ZIP auditado por CRC, presença do executável, Python/Tk e plano da interface;
  SHA-256 conferido com `dist/SHA256SUMS.txt`.
- O build emitiu avisos de coleta de módulos opcionais/de testes das dependências.
  Não impediram a geração, a abertura do aplicativo ou o smoke do worker.

A entrega é local. Não foi solicitado commit, push ou publicação de release.

## Limites

Não foram repetidos downloads em provedores externos, testes de desempenho,
exportação para pendrive ou rádio físico. O provedor da prévia é determinístico e
não valida disponibilidade de áudio real. Não houve certificação de todas as
escalas de texto/DPI do Windows. O redesenho preserva os serviços de biblioteca,
recuperação, classificação e exportação; no exportador só foi atualizado um texto
de orientação. A validação de uso será feita pelo usuário.

## Repetir a inspeção

Execute na raiz do projeto, com o ambiente de desenvolvimento ativado:

```powershell
python scripts/preview_ui.py --minimum
python scripts/preview_ui.py --minimum --empty
```

A prévia usa um catálogo temporário e não faz consultas de rede. `--page 0` a
`--page 3` escolhe a área inicial. Não está incluída como modo do executável final.
