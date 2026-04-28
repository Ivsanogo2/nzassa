# Setup IA Nzassa

Nzassa choisit automatiquement cet ordre:

1. `Ollama local`
2. `OpenRouter gratuit`
3. `Hugging Face`
4. `OpenAI`
5. `Mode local intelligent`

## Option 1: gratuite sans cle

Installe Ollama:

- [https://ollama.com/download](https://ollama.com/download)

Puis telecharge un modele:

```powershell
ollama pull qwen3:4b
```

Ensuite lance ton projet. Avec le fichier `.env` deja cree, Nzassa utilisera automatiquement Ollama.

## Option 2: gratuite avec cle

Cree une cle OpenRouter:

- [https://openrouter.ai/keys](https://openrouter.ai/keys)

Puis ajoute-la dans `.env`:

```env
OPENROUTER_API_KEY=ta_cle
```

Le modele par defaut est deja configure sur `openrouter/free`.

## Fichier `.env`

Le projet charge automatiquement le fichier `.env` a la racine.

Exemple deja prepare:

```env
NZASSA_AI_PROVIDER=auto
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_URL=http://localhost:11434/api/chat
OLLAMA_MODEL=qwen3:4b
DJANGO_DEBUG=True
```
