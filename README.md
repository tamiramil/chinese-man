# Chinese Man

Heyo, I know you need to solve all of these hundreds of boring as fuck problems. But here is your magic pill. This script automates CodingBat problems solving and mimics human behaviour (for CodingBat graphs). Yeah, the script doesn't make it instantly, it's a "process" instead, but who cares, when you can still spend this time on what matters. You can modify it if you want it to work instantly (or ask the author to do it for some reward).

---

## Quick Start

### 1. Prerequisites
    - Python 3.11+ (It's kinda weird you didn't get it on your PC).
    - Browsers: Chrome or Firefox installed (Safari if macOS).
    - API Key: Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/).

### 2. Installation

#### Windows (you better got linux):
``` PowerShell
git clone https://github.com/tamiramil/chinese-man.git
cd chinese-man
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

#### macOS / Linux:
``` bash
git clone https://github.com/tamiramil/chinese-man.git
cd chinese-man
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Note:** Don't push `config.toml` with your credentials to public (obviously).

### 3. Setup `config.toml`
**Main Rule:** Do read the fuckin' comments.
1. Copy `config.example.toml` content to `config.toml`.
2. Open the `config.toml` and fill int and/or change the config values.

### 4. Usage
**Note:** Always make sure your venv is active before running these.
    1. Sync: `python chinese-man.py sync`
        Logs in via Selenium, steals cookies, scrapes all tasks. Creates `repo_metadata.json`.
    2. Generate: `python chinese-man.py gen`
    Feeds tasks to Gemini. Generates T solutions per task (where T-1 are broken). Creates `ai_payloads.json`.
    3. Deploy: `python chinese-man.py deploy`
    The "Human Sim". Logs in and starts submitting solutions with randomized "thinking" delays.

---

## Technical Details & Troubleshooting

### The Workflow

**Authentication:** Uses Selenium to grab session cookies, then switches to requests for scraping and submission.

**The "Human" Factor:** The script doesn't just paste the right answer. It calculates a T number of attempts based on problem complexity. It will intentionally submit garbage/broken code T-1 times before submitting the correct one.

**Wait Times:** `base_think_time` is multiplied by the AI-assigned complexity. It's not a static timer; it's randomized.

### FAQ

"Will I get banned?" - Man, I don't know

"Will I get punished?" - Man, I don't know, the license is MIT, so my hata is on the edge
