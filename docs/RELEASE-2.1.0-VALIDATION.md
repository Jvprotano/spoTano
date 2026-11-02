# Conferência do pacote Windows 2.1.0

Gerado localmente em 31/10/2026, a partir do checkout atual, incluindo o redesenho
desktop, os ícones e os testes rápido e completo de configuração recomendada.

## Código e versão

- `pyproject.toml`, `spotano.__version__`, metadados locais e notas da versão em 2.1.0.
- Ruff passou em `spotano`, `scripts` e `tests`.
- Testes focados da calibração e da interface: **26 passed, 18 deselected**,
  executados novamente nesta entrega. A suíte geral não foi repetida neste build.
- PyInstaller 6.22.3 e Python 3.12.3. Os avisos de coleta de módulos opcionais/de
  testes não impediram a conclusão do empacotamento.

## Execução do binário

- `scripts/smoke_frozen.py` passou no `dist/spoTano/spoTano.exe`: imports do SDK,
  FFmpeg, transcodificação real de MP3 local gerado e eventos de progresso.
- `scripts/smoke_download_sessions.py` passou no executável: duas amostras próprias
  em loopback, um único processo/inicialização, progresso de transferência e
  conversão, MP3 validado e encerramento do worker, em 7,08 segundos.
- Abertura com catálogo novo e isolado confirmada: janela principal com título
  `spoTano · Sua música, com você`, responsiva. A instância de conferência foi
  encerrada após a verificação, sem alterar a biblioteca pessoal.
- A abertura foi conferida por processo/janela, sem nova inspeção visual por
  screenshot de todos os fluxos ou escalas de texto/DPI.

## Distribuição

Pacote portátil: `dist/spoTano-2.1.0-windows-x64.zip`. Extraia a pasta inteira e
abra `spoTano.exe`; Python já acompanha o programa. O executável precisa dos
arquivos da pasta. No primeiro uso, prepare os componentes em Configurações → Downloads.

A auditoria final exige correspondência do bytecode de oito módulos com o fonte
atual (`spotano`, entrada, benchmark, GUI, views, UI, branding e exporter), CRC do
ZIP íntegro, executável do ZIP idêntico ao da pasta, presença de Python, ícones,
licenças e documentação, inventário com `spotano==2.1.0`, ausência de catálogo
pessoal e checksum compatível com `dist/SHA256SUMS.txt`.

Evidências de desenvolvimento ficam em `artifacts/release-2.1.0/`, incluindo
`frozen-smoke.log`, `warm-frozen-smoke.log`, `startup.json` e `package-audit.json`.
O log de build fica em `dist/build-2.1.0.log`. O diretório de evidências não integra
o ZIP; o pacote contém esta documentação e as licenças.

## Pendências e limites

- Alguns testes gerais da interface ainda esperam controles removidos pelo
  redesenho, como `force_button`. Eles precisam ser adequados à interface atual;
  a suíte geral não deve ser apresentada como aprovada.
- Falta repetir a calibração completa com áudio do provedor real nas condições
  de uso. Ensaios com áudio gerado comprovam execução e integridade, sem prever
  disponibilidade ou desempenho do YouTube, nem compatibilidade com rádio físico.
- A entrega é local, sem commit/push, tag ou publicação no GitHub nesta etapa.

Método, custos e evidências anteriores em [PERFORMANCE-CALIBRATION.md](PERFORMANCE-CALIBRATION.md).
