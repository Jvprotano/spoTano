# Dependências e licenças

spoTano é software original sob GPL-3.0-or-later. O spotDL é uma dependência, sem fork nem
cópia do seu código-fonte no repositório. Sua licença MIT é reproduzida em
`docs/licenses/spotDL-MIT.txt`. O pacote Windows inclui os avisos e versões das
distribuições Python no diretório `licenses/` e os componentes Python/Tcl/Tk
coletados pelo PyInstaller. As licenças de cada dependência continuam aplicáveis.

- [spotDL](https://github.com/spotDL/spotify-downloader): MIT, metadados e obtenção de áudio.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp): Unlicense, com dependências de outras licenças.
- [Mutagen](https://github.com/quodlibet/mutagen): GPL-2.0-or-later.
- [Pykakasi](https://github.com/miurahr/pykakasi): GPL-3.0-or-later.
- [Unidecode](https://github.com/avian2/unidecode): GPL-2.0-or-later.
- [Python](https://docs.python.org/3/license.html): PSF e avisos de componentes; Tcl/Tk tem licença própria.
- [PyInstaller](https://pyinstaller.org/en/stable/license.html): GPL com exceção para distribuir aplicações empacotadas.
- [MusicBrainz](https://musicbrainz.org/doc/About/Data_License): metadados básicos CC0; dados suplementares CC BY-SA 3.0.

Os metadados pessoais, cache e áudios não são publicados pelo spoTano. As tags de
gênero consultadas são armazenadas localmente, sem espelhar a base MusicBrainz.

FFmpeg e Deno são ferramentas externas instaladas pelo usuário através da opção
**Preparar downloads**, usando os instaladores do spotDL. Seus binários não estão
incluídos no ZIP do spoTano. Consulte [FFmpeg](https://ffmpeg.org/legal.html) e
[Deno](https://github.com/denoland/deno/blob/main/LICENSE.md) para suas licenças.

A licença do software não concede direitos sobre músicas. A autorização para obter
e usar cada gravação e os termos do provedor precisam ser respeitados.

Cada release binária acompanha um arquivo `*-source.zip` com o código do spoTano,
receitas de build e fontes das dependências Python nas versões distribuídas.
O código original do spotDL permanece sob MIT; o conjunto distribuído com suas
dependências GPL é disponibilizado sob GPL-3.0-or-later.
