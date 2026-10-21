# speak — voz local para agentes de programação

Dá voz a agentes como o Claude Code: um comando `speak` que fala texto com [Piper](https://github.com/OHF-Voice/piper1-gpl) (offline, cerca de 0,1 s por frase), uma skill `speech` no formato aberto [Agent Skills](https://agentskills.io) e, no Claude Code, um hook que lê em voz alta cada resposta.

Não vem nenhuma voz incluída nem pré-definida: cada pessoa escolhe e instala a voz que quer usar (ver [Adicionar uma voz](#adicionar-uma-voz)).

## Requisitos

- Linux ou WSL2 (no WSL o som sai pelo servidor PulseAudio do WSLg).
- [uv](https://docs.astral.sh/uv/) (recomendado) ou Python 3.11+ com `python3-venv`.
- PortAudio para tocar o som: `sudo apt install libportaudio2 libasound2-plugins`. Sem ele o `speak` só grava ficheiros WAV.

## Instalação

```bash
git clone https://github.com/oriworks/ai-tts.git ~/ai-tts
cd ~/ai-tts
./install.sh                          # ou: ./install.sh --voice NOME
```

O instalador:

1. cria `.venv` com as dependências de `requirements.txt`;
2. escreve o comando `~/.local/bin/speak`;
3. cria `~/.config/speak/config.toml` e `~/.config/speak/pronunciations.txt`;
4. se indicares `--voice NOME`, descarrega essa voz para `~/.local/share/speak/voices`; sem essa opção não instala nenhuma voz;
5. liga a skill em `~/.agents/skills/speech` (pasta partilhada por agentes compatíveis) e, se existir `~/.claude`, em `~/.claude/skills/speech`;
6. no Claude Code, acrescenta a `~/.claude/settings.json` os hooks SessionStart (arranca o daemon) e Stop (fala a resposta) e a permissão `Bash(speak:*)`, guardando uma cópia em `settings.json.bak`;
7. liga o modo automático e, se houver voz, diz uma frase de teste.

Opções: `--voice NOME`, `--skills-dir DIR` (repetível, para pastas de skills de outros agentes), `--no-hooks`, `--no-auto`, `--no-test`. Pode correr-se outra vez sem duplicar nada, por exemplo depois de `git pull`.

## Utilização

```bash
speak "Olá, mundo."              # fala o texto
echo "texto" | speak             # ou a partir do stdin
speak --out frase.wav "Olá."     # também grava em WAV
speak --stop                     # pára o que está a tocar
speak --auto on|off|status       # modo automático (falar cada resposta)
speak --rate 1.3                 # ritmo (length_scale do Piper; maior é mais lento)
speak --list pt                  # vozes disponíveis (* = instaladas)
speak --use NOME                 # instala uma voz e passa a usá-la
```

No agente, basta pedir: "lê em voz alta", "desativa a voz", "fala mais devagar", "diz Kubernetes como Cubernétis"; no Claude Code também `/speech`.

O daemon mantém o modelo carregado (cerca de 240 MB) e termina sozinho após 30 minutos sem pedidos.

## Adicionar uma voz

As vozes são modelos Piper publicados por terceiros no repositório [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices). Para adicionar uma:

1. Vê as vozes disponíveis, filtrando pela língua se quiseres:
   ```bash
   speak --list pt      # ou en, en_GB, es, fr...
   ```
   Cada linha mostra o nome da voz e a ligação para o `MODEL_CARD`.
2. Abre o `MODEL_CARD` e lê a licença da voz e do conjunto de dados com que foi treinada. Se a voz foi afinada a partir de outra, lê também a licença dessa voz de base.
3. Instala-a e passa a usá-la:
   ```bash
   speak --use NOME
   ```
   Isto descarrega o modelo para `~/.local/share/speak/voices` e escreve `voice = "..."` em `~/.config/speak/config.toml`. Podes ter várias vozes instaladas e trocar com `speak --use`, ou usar uma só vez com `speak --voice NOME "texto"`.

Algumas vozes que podem ser adicionadas (lista completa com `speak --list`):

| Voz | Língua | Cartão do modelo |
|---|---|---|
| `pt_PT-tugão-medium` | Português (Portugal) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/pt/pt_PT/tug%C3%A3o/medium/MODEL_CARD) |
| `pt_BR-cadu-medium` | Português (Brasil) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/pt/pt_BR/cadu/medium/MODEL_CARD) |
| `pt_BR-faber-medium` | Português (Brasil) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/pt/pt_BR/faber/medium/MODEL_CARD) |
| `pt_BR-jeff-medium` | Português (Brasil) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/pt/pt_BR/jeff/medium/MODEL_CARD) |
| `en_US-amy-medium` | Inglês (EUA) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/amy/medium/MODEL_CARD) |
| `en_US-lessac-medium` | Inglês (EUA) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD) |
| `en_US-ryan-medium` | Inglês (EUA) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ryan/medium/MODEL_CARD) |
| `en_GB-alan-medium` | Inglês (Reino Unido) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/alan/medium/MODEL_CARD) |
| `en_GB-cori-medium` | Inglês (Reino Unido) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/cori/medium/MODEL_CARD) |
| `es_ES-davefx-medium` | Espanhol (Espanha) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_ES/davefx/medium/MODEL_CARD) |
| `es_ES-sharvard-medium` | Espanhol (Espanha) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_ES/sharvard/medium/MODEL_CARD) |
| `es_MX-ald-medium` | Espanhol (México) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_MX/ald/medium/MODEL_CARD) |
| `fr_FR-siwis-medium` | Francês (França) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD) |
| `fr_FR-tom-medium` | Francês (França) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/tom/medium/MODEL_CARD) |
| `de_DE-thorsten-medium` | Alemão (Alemanha) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/de/de_DE/thorsten/medium/MODEL_CARD) |
| `it_IT-paola-medium` | Italiano (Itália) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/it/it_IT/paola/medium/MODEL_CARD) |
| `nl_NL-pim-medium` | Neerlandês (Países Baixos) | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/nl/nl_NL/pim/medium/MODEL_CARD) |

Esta lista é apenas uma conveniência. Não é uma recomendação nem uma garantia de que alguma destas vozes possa ser usada para um fim concreto.

### Responsabilidade pelo uso das vozes

Este projecto não inclui, não distribui nem escolhe nenhuma voz. O `speak` só descarrega a voz que o utilizador pede, directamente do repositório público onde foi publicada. As vozes têm licenças próprias, definidas por quem as criou. Algumas derivam de conjuntos de dados com restrições, por exemplo apenas para investigação ou sem uso comercial.

Cabe a quem usa a aplicação verificar a licença de cada voz que instala e cumpri-la. Os autores deste projecto não dão nenhuma garantia sobre as vozes de terceiros nem assumem responsabilidade pelo uso que lhes for dado. Esta exclusão de garantia e de responsabilidade está também nas secções 15 e 16 da licença GPL-3.0.

A limpeza de símbolos do modo automático conhece português e inglês; noutras línguas os símbolos são apenas retirados.

## Pronúncias

`~/.config/speak/pronunciations.txt` tem linhas `termo = como dizer`, com uma grafia na língua da voz ou fonemas IPA entre `[[ ]]`. Os termos são procurados como palavras inteiras, sem distinguir maiúsculas. As alterações valem logo na fala seguinte. O ficheiro inicial é copiado de `pronunciations/<língua>.txt` quando existe um para a língua da voz (por agora só `pt_PT`). Se trocares de língua, revê ou apaga este ficheiro. Contribuições para outras línguas são bem-vindas.

## Outros agentes

O comando `speak` funciona em qualquer agente com acesso à shell, e a skill segue o formato Agent Skills. Se o teu agente não lê `~/.agents/skills`, liga a skill à pasta dele com `./install.sh --skills-dir ~/.<agente>/skills`.

Para falar cada resposta automaticamente, usa o hook de fim de turno do agente para enviar o texto final para `speak` (por exemplo `printf '%s' "$RESPOSTA" | speak`), respeitando `speak --auto status`. O adaptador incluído (`autospeak.py`) é específico do Claude Code: lê o JSON do hook Stop e limpa o markdown antes de falar.

## Desinstalar

```bash
./install.sh --uninstall
```

Remove os hooks, a permissão, as ligações da skill, o comando e o estado em `~/.cache/speak`, e pergunta se deve apagar vozes e configuração. Depois podes apagar o clone.

## Licença

Código sob a licença GNU GPL, versão 3 ou posterior (ver `LICENSE`), a mesma do Piper, de que depende.

A licença do código não se aplica às vozes. Ver [Responsabilidade pelo uso das vozes](#responsabilidade-pelo-uso-das-vozes).
