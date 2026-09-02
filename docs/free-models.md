# Running cubicle on a free model

You do not need a paid API account to put a model on this leaderboard.

Every provider below speaks the same OpenAI-compatible chat API, so cubicle talks to all
of them through one adapter (`cubicle/agents/openai_compat.py`). Adding a model is three
environment variables and no code.

```bash
CUBICLE_VISION_BASE_URL=https://openrouter.ai/api/v1
CUBICLE_VISION_MODEL=qwen/qwen2.5-vl-72b-instruct:free
CUBICLE_VISION_API_KEY=sk-or-...

python scripts/check_vision.py          # one cheap call: does it work at all?
python scripts/vision_probe.py setup-verify.png   # can it point? one call, no desktop
python scripts/run.py --agent vision --tasks all  # the full benchmark
```

**The model must accept images.** A text-only model will connect fine and then fail every
step, which looks like a capability result and is not one. `check_vision.py` sends an
image on purpose so this shows up immediately.

---

## Free, unmetered, no signup: run it on your own machine

The only option with no quota, no card and no account. Slower than a hosted API, and
limited by your VRAM, but you can run it all night for nothing.

1. Install [Ollama](https://ollama.com/download).
2. Pull a vision model. On 6-8GB of VRAM:
   ```bash
   ollama pull qwen2.5vl:3b        # good general vision, small
   ollama pull moondream           # 1.8B, very small
   ollama pull llava:7b            # older, widely available
   ```
   Check what a model needs before pulling — Ollama lists sizes on its model pages.
3. Point cubicle at it. **No API key** — the adapter allows a missing key for loopback
   addresses precisely so this works:
   ```bash
   CUBICLE_VISION_BASE_URL=http://localhost:11434/v1
   CUBICLE_VISION_MODEL=qwen2.5vl:3b
   ```

### Why local is the interesting one here

The open GUI-grounding models — **ShowUI-2B**, **OS-Atlas**, **UI-TARS**, **Holo1** — are
post-trained specifically to point at interface elements. That is exactly the capability
this benchmark reports on, and none of the models measured so far have it.

Some are not packaged for Ollama and need `transformers` directly. That is more work than
an API call, and it is the most direct answer to the obvious objection: *you only tested
models that were never taught to point.*

---

## Free tiers, signup only, no card

Sign up, create a key, paste it in. Limits and model ids change often — check the
provider's own model list rather than trusting the ids below.

| Provider | `CUBICLE_VISION_BASE_URL` | Getting a key |
|---|---|---|
| **OpenRouter** | `https://openrouter.ai/api/v1` | openrouter.ai → Keys. Models with a `:free` suffix cost nothing. Best single signup — many models behind one key. |
| **Groq** | `https://api.groq.com/openai/v1` | console.groq.com → API Keys. Fast, generous free tier. Use a vision-capable model. |
| **GitHub Models** | see note below | github.com/marketplace/models — free with a GitHub account, uses a PAT. |
| **NVIDIA NIM** | `https://integrate.api.nvidia.com/v1` | build.nvidia.com — free credits on signup, hosts many open VLMs. |
| **Mistral** | `https://api.mistral.ai/v1` | console.mistral.ai — free experiment tier; Pixtral is the vision model. |
| **Together** | `https://api.together.xyz/v1` | api.together.ai — small free credit on signup. |
| **Cerebras** | `https://api.cerebras.ai/v1` | cloud.cerebras.ai — free tier, mostly text; check for vision support. |
| **Hugging Face** | router endpoint, see their docs | huggingface.co/settings/tokens — free monthly inference credits. |

**GitHub Models** has moved its endpoint at least once. Take the base URL from their
current docs rather than from here.

## What you may already have

- **Google AI Studio** (`GEMINI_API_KEY`) — free, and the daily cap is **per model**, so
  spreading probes across models buys far more than hammering one. Note that
  `gemini-2.5-computer-use-preview` returns 429 on **any** free-tier call: its free
  allowance is zero, so it is paid-only despite the quota metric naming a free tier.
- **DeepSeek** (`DEEPSEEK_API_KEY`) — paid, already wired up as its own agent.

## Verifying before you spend a desktop

```bash
python scripts/check_vision.py
```

One image request against the configured endpoint. It prints the status, the model that
answered and the first line of the reply, and never prints your key. Run it before
`run.py`, because a full run costs Solari desktop time and a 401 four minutes in is a
waste of it.
