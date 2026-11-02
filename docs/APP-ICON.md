# Ícone do spoTano

Criado em 30/10/2026 com imagegen: nota musical em marfim com seta integrada,
sobre um fundo quadrado verde. O símbolo acompanha a proposta "Sua música,
com você" e as cores da interface desktop. A arte original foi preservada em
`spotano/assets/spotano.png`, com fundo opaco para manter a legibilidade em
superfícies claras e escuras.

`scripts/build_icons.py` usa Pillow (incluído em `requirements-lock.txt`) para
gerar `spotano.ico` com 16, 20, 24, 32, 40, 48, 64, 128 e 256 pixels e os PNGs
de 16, 32, 48 e 256 usados pelo Tkinter. O ICO usa quadros DIB para compatibilidade
com o leitor nativo de ícones do Tk no Windows. Execute com o ambiente do projeto:

```powershell
.venv\Scripts\python.exe scripts/build_icons.py
```

Os arquivos derivados ficam versionados; o usuário final não precisa gerar
imagens nem instalar Pillow separadamente. O PyInstaller embute o ICO no EXE e
copia os recursos para `spotano/assets`. O setuptools inclui os PNGs/ICO nos
pacotes Python. `spotano/branding.py` resolve os recursos em relação ao módulo,
sem depender do diretório em que o aplicativo foi aberto.

A identidade da barra de tarefas usa o identificador estável `Jvprotano.spoTano`.
Os atalhos criados para `spoTano.exe` usam seu ícone embutido. Esta versão continua
sendo distribuída como ZIP portátil: extraia a pasta inteira antes de abrir.
