# J.A.R.V.I.S — Just A Rather Very Intelligent System

> **Criado e desenvolvido por Senhor Victor**

Assistente pessoal de IA com voz masculina, inspirado no JARVIS do filme Homem de Ferro.
Interface 100% local, rodando no seu PC, bilíngue (PT-BR / EN-US), com visão de tela e câmera.

---

## Índice

1. [Requisitos](#requisitos)
2. [Instalação passo a passo](#instalação)
3. [Configuração das APIs](#configuração-das-apis)
4. [Como iniciar](#como-iniciar)
5. [Como usar](#como-usar)
6. [Comandos de voz](#comandos-de-voz)
7. [Funcionalidades detalhadas](#funcionalidades)
8. [Solução de problemas](#solução-de-problemas)
9. [Estrutura de arquivos](#estrutura)

---

## Requisitos

- Windows 10 ou 11 (64-bit)
- Python 3.10, 3.11 ou 3.12
- Google Chrome instalado
- Microfone funcionando
- Câmera (opcional — para visão)
- Conexão com internet
- Chave de API: **Groq** (gratuita) ou **OpenAI**

---

## Instalação

### Passo 1 — Instale o Python

Baixe em: https://www.python.org/downloads/
Durante a instalação, marque ✅ **"Add Python to PATH"**

Para verificar:
```powershell
python --version
```
Deve mostrar `Python 3.11.x` ou similar.

---

### Passo 2 — Extraia o JARVIS

Extraia o ZIP em uma pasta de sua preferência, por exemplo:
```
C:\JARVIS\
```

A estrutura deve ser:
```
C:\JARVIS\
├── backend\
│   └── jarvis_core.py
├── frontend\
│   └── index.html
├── requirements.txt
├── start_jarvis.bat
└── README.md
```

---

### Passo 3 — Abra o PowerShell na pasta

Navegue até a pasta do JARVIS no PowerShell:
```powershell
cd C:\JARVIS
```

---

### Passo 4 — Instale as dependências

```powershell
pip install -r requirements.txt
```

Se algum pacote der erro, instale individualmente:
```powershell
pip install flask flask-cors flask-socketio
pip install openai groq
pip install SpeechRecognition
pip install selenium webdriver-manager
pip install pillow opencv-python numpy
pip install psutil sounddevice requests beautifulsoup4
pip install pywin32
```

> ⚠️ **Não precisa** instalar PyAudio manualmente.
> O JARVIS usa `sounddevice` para detecção de palmas e `SpeechRecognition` com o microfone nativo.

---

### Passo 5 — (Opcional) Instale mss para captura de tela multi-monitor

```powershell
pip install mss pyautogui
```

---

## Configuração das APIs

Você precisa de **pelo menos uma** chave de API para o JARVIS pensar e responder.

### Groq (GRATUITO — recomendado para começar)

1. Acesse: https://console.groq.com/keys
2. Crie uma conta (gratuita)
3. Clique em **"Create API Key"**
4. Copie a chave (começa com `gsk_...`)

### OpenAI (para visão de tela/câmera — requer créditos)

1. Acesse: https://platform.openai.com/api-keys
2. Clique em **"Create new secret key"**
3. Copie a chave (começa com `sk-...`)

> 💡 **Dica:** O JARVIS usa Groq automaticamente se a OpenAI falhar ou não tiver créditos.
> Para usar a câmera e análise de imagens, a OpenAI é necessária (GPT-4o Vision).

---

### Configurar as chaves

**Opção A — Pelo painel visual (mais fácil):**
1. Inicie o JARVIS
2. Clique no ícone ⚙ (Config) no canto inferior
3. Cole suas chaves nos campos
4. Clique em **SALVAR**

**Opção B — Editando o arquivo config.json:**

Crie (ou edite) o arquivo `backend\config.json`:
```json
{
  "openai_api_key": "sk-...",
  "groq_api_key": "gsk_...",
  "wake_word": "jarvis",
  "city": "Piracicaba",
  "owner": "Senhor Victor",
  "intro_music": "random",
  "speech_rate": 1,
  "volume": 100
}
```

---

## Como iniciar

### Opção 1 — Arquivo BAT (mais fácil)

Dê duplo clique em:
```
start_jarvis.bat
```

### Opção 2 — PowerShell

```powershell
cd C:\JARVIS
python backend\jarvis_core.py
```

### Opção 3 — Como Administrador (se der erro de permissão)

Clique com botão direito no PowerShell → **"Executar como administrador"** → rode o comando acima.

---

Após iniciar, abra o navegador em:
```
http://localhost:5000
```

---

## Como usar

### Ativação inicial — 2 palmas 👋👋

Na primeira vez, o JARVIS aguarda **2 palmas** para acordar.

1. Fique perto do microfone
2. Bata palmas **2 vezes** em ritmo normal (não muito rápido)
3. O JARVIS vai:
   - Tocar uma música de entrada (AC/DC ou similar)
   - Dar as boas-vindas com voz masculina
   - Falar o clima da sua cidade
   - Contar as principais notícias do dia
4. A interface muda: o ícone de palmas some e o campo de texto aparece

### Wake Word — diga "JARVIS"

Após ativado, fale **"JARVIS"** + seu comando:
```
"JARVIS, que horas são?"
"JARVIS, toca Thunderstruck"
"JARVIS, como está o clima?"
```

O JARVIS responde automaticamente, sem apertar nenhum botão.

### Microfone manual 🎤

Clique no botão do microfone para falar sem precisar dizer "JARVIS" antes.

### Texto

Digite qualquer comando no campo de texto e pressione Enter ou clique em ↑

---

## Ícones da interface

| Ícone | Função |
|-------|--------|
| 🔇 | **Mudo** — JARVIS continua respondendo mas só mostra o texto (não fala) |
| ⏹ | **Interromper** — Para a fala imediatamente no meio da resposta |
| 🎤 | **Microfone** — Ativa escuta manual (sem precisar dizer JARVIS) |
| 👁 | **Visão** — Liga/desliga câmera ao vivo |
| ⚙ | **Config** — Abre o painel de configurações |

---

## Comandos de voz

### Músicas
```
"JARVIS, toca Thunderstruck"
"JARVIS, toca Back in Black"
"JARVIS, toca Should I Stay or Should I Go"
"JARVIS, toca Highway to Hell"
"JARVIS, toca Iron Man"
"JARVIS, toca [qualquer música]"
```

### Clima e notícias
```
"JARVIS, como está o clima?"
"JARVIS, clima em São Paulo"
"JARVIS, notícias de hoje"
"JARVIS, notícias de Piracicaba"
```

### Abrir apps e sites
```
"JARVIS, abre o YouTube"
"JARVIS, abre o Spotify"
"JARVIS, abre o WhatsApp"
"JARVIS, abre o VS Code"
"JARVIS, abre o Chrome"
"JARVIS, abre o Gmail"
"JARVIS, abre a calculadora"
"JARVIS, abre o Netflix"
```

### Visão de tela
```
"JARVIS, ver tela"
"JARVIS, o que está na minha tela?"
"JARVIS, lê a minha tela"
"JARVIS, transcrever tela"
```

### Câmera
```
"JARVIS, o que a câmera vê?"
"JARVIS, identifica o que vê"
"JARVIS, olha pela câmera"
```

### Código
```
"JARVIS, corrige o código"
"JARVIS, analisa o código na tela"
"JARVIS, revisa o código"
```

### PC e sistema
```
"JARVIS, status do sistema"
"JARVIS, desligar o PC em 30 minutos"
"JARVIS, cancelar desligamento"
```

### Memória e planos
```
"JARVIS, lembre que eu prefiro café sem açúcar"
"JARVIS, memorize que minha senha do wifi é 1234"
"JARVIS, criar plano academia"
"JARVIS, meus planos"
```

### Inglês e tradução
```
"JARVIS, fala inglês"           → muda para modo inglês
"JARVIS, fala português"        → volta para português
"JARVIS, teach me English"      → aula de inglês
"JARVIS, traduz: I love pizza"  → tradução PT↔EN
"JARVIS, how do you say 'saudade' in English?"
```

### Hora e data
```
"JARVIS, que horas são?"
"JARVIS, que dia é hoje?"
```

### Sobre o JARVIS
```
"JARVIS, quem te criou?"
→ "Fui criado e desenvolvido pelo Senhor Victor, Senhor."
```

---

## Funcionalidades

### 🧠 Inteligência Artificial
- **OpenAI GPT-4o-mini** para conversas gerais
- **Groq LLaMA 3.3 70B** como fallback gratuito
- Troca automática se uma API falhar ou ficar sem créditos
- Mantém contexto da conversa em todas as respostas

### 💾 Memória de 2 Meses
- Lembra de tudo que você pediu para guardar
- Histórico de conversas dos últimos 60 dias
- Contexto de planos e metas ativos
- Arquivo local: `backend/jarvis_memory.json`

### 🎙️ Voz Masculina (Antonio/David)
- Usa o motor SAPI do Windows diretamente
- Prioriza voz **Antonio** (pt-BR masculina nativa do Windows 11)
- Fallback automático para David (en-US) ou qualquer masculina disponível
- Sem dependência de PyAudio ou pyttsx3

### 🌐 Bilíngue PT-BR / EN-US
- Detecta automaticamente se você falou em português ou inglês
- Responde no mesmo idioma que você usou
- Pode ensinar inglês com frases, pronúncia e tradução
- Tradução em tempo real dos dois lados

### 👁️ Visão de Tela
- Captura a tela inteira com 3 métodos (PIL, mss, pyautogui)
- Descreve o que está na tela
- Lê e transcreve textos
- Analisa e corrige código com GPT-4o Vision
- Requer chave OpenAI para análise

### 📷 Câmera
- Detecta câmera automaticamente (testa índices 0, 1, 2)
- Identifica pessoas, objetos e texto em tempo real
- Stream ao vivo na interface (ícone 👁)
- Captura único frame para análise sob demanda

### 🎵 Músicas no YouTube
- Abre e toca diretamente no Chrome via Selenium
- Fecha a aba automaticamente após 60 segundos
- Repertório: Thunderstruck, Back in Black, Should I Stay, Highway to Hell, Iron Man, Shoot to Thrill, Hells Bells
- Sorteia aleatoriamente na inicialização
- Aceita qualquer música por nome

### 🌤️ Clima em Tempo Real
- Usa wttr.in (sem API key, sem navegador)
- Temperatura, sensação térmica, máxima, mínima, umidade, vento
- Funciona para qualquer cidade do mundo
- Pergunta na inicialização automaticamente

### 🏠 Home Assistant
- Controla luzes por cômodo
- Sala, quarto, cozinha, banheiro, escritório
- Configure URL e token no painel ⚙

### 💻 Controle do PC
- Abre mais de 30 aplicativos Windows por voz
- Agenda desligamento com timer
- Monitora CPU, memória e disco
- Abre qualquer executável ou site

---

## Solução de problemas

### Microfone não funciona
1. Windows → Configurações → Privacidade → Microfone
2. Ative o acesso para **Python** e para o **Navegador**
3. Verifique se o microfone correto está selecionado como padrão no Windows

### Palmas não detectadas
- Fique a até 1 metro do microfone
- Bata as palmas com força moderada
- O intervalo entre as palmas deve ser de 0.3 a 1.4 segundos
- Se não funcionar, use o botão 🎤 ou o campo de texto

### Câmera não funciona
```powershell
pip install opencv-python
```
- Verifique se a câmera não está em uso por outro programa (Teams, Zoom, etc.)
- Ative permissão de câmera para Python nas configurações do Windows

### Captura de tela não funciona
```powershell
pip install mss pyautogui pillow
```
- Execute o PowerShell como **Administrador** na primeira vez

### Voz masculina não aparece
O Windows 11 já inclui a voz **Antonio (pt-BR)**.
Se não tiver, adicione em:
**Configurações → Hora e idioma → Fala → Adicionar vozes → Português (Brasil)**

### Erro de permissão no TTS
Execute como **Administrador** uma única vez para gerar o cache do SAPI.

### Chrome não abre
```powershell
pip install webdriver-manager selenium
```
Certifique-se que o Google Chrome está instalado no PC.

### API sem resposta
- Verifique sua conexão com a internet
- Confirme que a chave foi colada corretamente (sem espaços)
- Teste sua chave Groq em: https://console.groq.com
- O JARVIS tenta OpenAI primeiro, depois Groq automaticamente

---

## Estrutura de arquivos

```
JARVIS/
├── backend/
│   ├── jarvis_core.py        ← Backend principal (Python)
│   ├── config.json           ← Suas configurações (criado na primeira execução)
│   ├── jarvis_memory.json    ← Memória de conversas e fatos (2 meses)
│   └── .deps_ok              ← Marcador de dependências instaladas
│
├── frontend/
│   └── index.html            ← Interface visual (HTML/CSS/JS)
│
├── requirements.txt          ← Lista de dependências Python
├── start_jarvis.bat          ← Inicialização no Windows
└── README.md                 ← Este arquivo
```

---

## Privacidade

- Todo o processamento de voz é feito localmente (SpeechRecognition + Google Speech API gratuita)
- A memória fica salva **apenas no seu computador** (`jarvis_memory.json`)
- As chaves de API ficam salvas localmente em `config.json`
- Imagens da câmera e tela **não são armazenadas**, apenas enviadas temporariamente para análise

---

## Créditos

**Criado e desenvolvido por Victor G.**

Inspirado no JARVIS do Universo Marvel / Homem de Ferro de Tony Stark.

*"Sua armadura está pronta, Senhor(a)."*

## Caso deseje modificar algo ou adicionar peça ao autor.
Email para dúvidas: suporte.dev.victor@gmail.com