# ELearning Video Generator

Transformez une présentation PowerPoint + narration audio + script texte en vidéo e-learning MP4 synchronisée.

## Démarrage rapide avec Docker Desktop

### 1 — Cloner le dépôt

```bash
git clone https://github.com/makcpp/claude-elearning
cd claude-elearning
git checkout claude/affectionate-mayer-wUbT4
```

### 2 — Lancer avec Docker Compose (recommandé)

```bash
docker compose up --build
```

> La première fois, le build télécharge les dépendances (~800 Mo). Les démarrages suivants sont instantanés.

Ouvrez ensuite **http://localhost:8000** dans votre navigateur.

### 3 — Ou avec Docker seul

```bash
# Build
docker build -t elearning-generator .

# Run
docker run -p 8000:8000 elearning-generator
```

---

## Utilisation

1. **Narration audio** — fichier MP3, WAV, M4A… de la voix qui lit le cours
2. **Texte de narration** — le script exact lu dans l'audio (`.txt`)
3. **Présentation** — fichier PowerPoint (`.pptx`, `.ppt`) ou ODP
4. **Modèle LLM** — choisir Claude Sonnet (Anthropic) ou GPT-4o (OpenAI)
5. **Clé API** — clé `sk-ant-…` (Anthropic) ou `sk-…` (OpenAI)
6. Cliquer **▶ Générer la vidéo e-learning**

La vidéo MP4 générée peut être prévisualisée et téléchargée directement dans le navigateur.

---

## Pipeline technique

```
PPTX  ──►  LibreOffice / Pillow  ──►  PNG slides
Text  ──►  LLM (Claude / GPT)    ──►  1 segment texte / slide
Audio ──►  FFmpeg split           ──►  1 chunk audio / slide
                                        │
                                        ▼
                              FFmpeg assemble ──► MP4 1920×1080
```

## Modèles supportés

| Fournisseur | Modèles |
|-------------|---------|
| Anthropic   | Claude Opus 4.7, **Sonnet 4.6** (défaut), Haiku 4.5, Claude 3.5 Sonnet/Haiku |
| OpenAI      | GPT-4o, GPT-4o Mini, GPT-4 Turbo |

## Formats supportés

| Type | Formats |
|------|---------|
| Audio | MP3, WAV, M4A, OGG, AAC, FLAC, WMA |
| Texte | TXT, MD |
| Présentation | PPTX, PPT, ODP |
| Sortie vidéo | MP4 (H.264, AAC, 1920×1080) |
