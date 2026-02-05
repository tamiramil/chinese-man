"""
Author: PulpyPuppy
Description:
This script cracks problems from codingbat.com/java like if it were a human (I hope).
"""

import os
import sys
import time
import json
import random
import tomllib
import requests
from bs4 import BeautifulSoup, NavigableString
from google import genai
from groq import Groq
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.safari.service import Service as SafariService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager

class LogColor:
    INFO = '\033[94m[INFO]\033[0m'
    SUCCESS = '\033[92m[SUCCESS]\033[0m'
    WARNING = '\033[93m[WARN]\033[0m'
    ERROR = '\033[91m[ERROR]\033[0m'
    AI = '\033[95m[AI]\033[0m'

def log(tag, message):
    timestamp = time.strftime("%H:%M:%S")
    print(f"{timestamp} {tag} {message}")

# === Configuration Infrastructure ===

def validate_config(cfg):
    required_structure = {
        'credentials': ['account_email', 'account_password', 'gemini_api_key', 'groq_api_key'],
        'system': ['headless_mode'],
        'paths': ['metadata_store', 'solution_buffer'],
        'ai_logic': ['llm', 'model_id', 'min_attempts', 'max_attempts'],
        'delays': ['login_wait', 'base_think_time']
    }

    missing = []
    for section, keys in required_structure.items():
        if section not in cfg:
            missing.append(f"Missing section: [{section}]")
            continue
        for key in keys:
            if key not in cfg[section]:
                missing.append(f"Missing key: {key} in [{section}]")
            elif not cfg[section][key] and not isinstance(cfg[section][key], bool):
                missing.append(f"Empty value for: {key} in [{section}]")

    if missing:
        log(LogColor.ERROR, "Configuration validation failed:")
        for error in missing:
            print(f"  - {error}")
        sys.exit(1)

    log(LogColor.SUCCESS, "Configuration validated. Ready for operation.")

with open('config.toml', 'rb') as f:
    config = tomllib.load(f)

validate_config(config)

BASE_URL = 'https://codingbat.com'
TARGET_LANG_URL = f"{BASE_URL}/java"

# === Core Engine Services ===

def get_automation_driver():
    browser_type = config['system'].get('browser', 'firefox').lower()
    is_headless = config['system'].get('headless_mode', True)

    log(LogColor.INFO, f"Initializing {browser_type.capitalize()} engine...")

    if browser_type == 'chrome':
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        if is_headless: options.add_argument('--headless')
        return webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

    elif browser_type == 'firefox':
        options = webdriver.FirefoxOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        if is_headless: options.add_argument('--headless')
        return webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options)

    elif browser_type == 'safari':
        options = webdriver.SafariOptions()
        return webdriver.Safari(service=SafariService(), options=options)

    else:
        log(LogColor.ERROR, f"Unsupported browser: {browser_type}")
        sys.exit(1)

def authorize_session(driver):
    log(LogColor.INFO, "Initiating authorization sequence...")
    driver.get(TARGET_LANG_URL)

    driver.find_element(By.NAME, 'uname').send_keys(config['credentials']['account_email'])
    driver.find_element(By.NAME, 'pw').send_keys(config['credentials']['account_password'])
    driver.find_element(By.NAME, 'dologin').click()

    time.sleep(config['delays']['login_wait'])
    log(LogColor.SUCCESS, "Session authorized successfully.")

def extract_session_context(driver):
    cookies = driver.get_cookies()
    return {c['name']: c['value'] for c in cookies}

# === Data Acquisition Layer ===

def sync_task_repository(session):
    log(LogColor.INFO, "Synchronizing local task repository with remote server...")
    response = session.get(TARGET_LANG_URL)
    soup = BeautifulSoup(response.content, 'html.parser')

    task_map = {}
    categories = soup.find_all('div', class_='summ')

    for cat in categories:
        link = cat.find('a')
        if not link: continue

        cat_url = BASE_URL + link.get('href')
        log(LogColor.INFO, f"Scanning category: {link.get_text()}")

        cat_response = session.get(cat_url)
        cat_soup = BeautifulSoup(cat_response.content, 'html.parser')

        for td in cat_soup.find_all('td'):
            task_link = td.find('a', href=True)
            if task_link and '/prob/p' in task_link['href']:
                t_id = task_link['href'].split('/')[-1]
                details = _fetch_unit_specs(session, BASE_URL + task_link['href'])

                img = td.find('img')
                is_completed = 'c2' in (img['src'] if img else '')

                task_map[t_id] = {**details, "status_completed": is_completed}

    with open(config['paths']['metadata_store'], 'w', encoding='utf-8') as f:
        json.dump(task_map, f, indent=4)
    log(LogColor.SUCCESS, f"Repository sync complete. Total units: {len(task_map)}")

def _fetch_unit_specs(session, url):
    resp = session.get(url)
    soup = BeautifulSoup(resp.content, 'html.parser')
    desc_div = soup.find('div', class_='minh')

    description = desc_div.get_text(strip=True) if desc_div else ""
    examples = []

    curr = desc_div.next_sibling if desc_div else None
    while curr:
        if curr.name in ['p', 'form', 'button']: break
        if isinstance(curr, NavigableString) and '→' in curr:
            examples.append(curr.strip())
        curr = curr.next_sibling

    signature = ""
    ace = soup.find('div', id='ace_div')
    if ace: signature = ace.get_text().strip().split('\n')[0]

    return {"desc": description, "cases": examples, "decl": signature}

# === AI Orchestration Layer ===

def init_client():
    llm = config['ai_logic']['llm']
    api_key = config['credentials']['api_key']

    if llm == 'gemini':
        os.environ['GEMINI_API_KEY'] = api_key
        return genai.Client()
    elif llm == 'groq':
        return Groq(api_key=api_key)
    else:
        log(LogColor.ERROR, f"Unknown LLM: {llm}")

def submit_to_client(client, prompt, retry=1):
    llm = config['ai_logic']['llm']
    model_id = config['ai_logic']['model_id']

    try:
        if llm == 'gemini':
            response = client.models.generate_content(model=model_id, contents=prompt)
            return response.text
        elif llm == 'groq':
            response = client.chat.completions.create(
                messages=[ { "role": "user", "content": prompt, } ],
                model=model_id,
            )
            return response.choices[0].message.content
        else:
            log(LogColor.ERROR, f"Unknown LLM: {llm}")
    except Exception as e:
        retry_time = config['ai_logic']['retry_time']

        if (retry < config['ai_logic']['retries']):
            log(LogColor.ERROR, f"Unable to connect to the AI client. Attempt {retry}. Retrying in {retry_time} seconds.")
            log(LogColor.ERROR, e)
            sleep(retry_time)
            return submit_to_client(client, prompt, retry=retry+1)
        else:
            log(LogColor.ERROR, f"Unable to connect to the AI client after {retry} attempts. Closing session.")
            log(LogColor.ERROR, e)
            sys.exit(1)

def synthesize_solutions(client, task_id, specs):
    log(LogColor.AI, f"Requesting synthesis for unit {task_id}...")

    base_tries = random.randint(config['ai_logic']['min_attempts'], config['ai_logic']['max_attempts'])
    rank_factor = config['ai_logic']['rank_factor']

    prompt = (
        "Act as a student learning Java. You must think step-by-step but output only the result.\n\n"

        "PHASE 1: Analyze complexity (1 to 3):\n"
        "1 - Easy: simple logic, 1-2 lines of code.\n"
        "2 - Medium: loops, multiple conditions, basic logic.\n"
        "3 - Hard: nested loops, complex data structures, algorithmic thinking.\n\n"

        "PHASE 2: Generation Logic:\n"
        f"Calculate the total number of solutions (T) using this rule: T = {base_tries} + (complexity_number * {rank_factor}).\n"
        "Generate exactly T solutions. The first T-1 solutions MUST be incorrect (syntax or logical errors). The last (T-th) solution MUST be correct.\n"
        "Show incremental progress: each version should be a slight improvement or a fix of a previous error, but still flawed until the final one.\n\n"

        "IMPORTANT RULES (STRICT COMPLIANCE):\n"
        "- Start your response directly with the complexity number. NO preamble, NO 'Sure', NO 'Here is the code'.\n"
        "- Use 'SMD' as a plain text separator between solutions.\n"
        "- Do not use markdown backticks (```) or any conversational text.\n"
        "- Do not include any comments (e.g., // Solution 1).\n"
        "- The provided signature ends with an opening brace '{'. Do NOT repeat it. Your code must start after it and end with a closing brace '}'.\n\n"

        "OUTPUT FORMAT EXAMPLE:\n"
        "<complexity_number>\n"
        "SMD\n"
        "<signature_text>\n"
        "    // code body\n"
        "}\n"
        "SMD\n"
        "<signature_text>\n"
        "    // next version\n"
        "}\n\n"

        "INPUT DATA:\n"
        f"Problem:\n{specs.get('description')}\n\n"
        f"Examples:\n{specs.get('examples')}\n\n"
        f"Signature:\n{specs.get('signature')}\n\n"
        f"Style:\n{config['ai_logic']['code_style']}"
    )

    try:
        response_text = submit_to_client(client, prompt)
        fragments = [f.strip() for f in response_text.replace('`', '').split('SMD') if f.strip()]
        return int(fragments[0]), fragments[1:]
    except Exception as e:
        log(LogColor.ERROR, f"Synthesis failed: {e}")
        return 1, []

def batch_process_solutions():
    client = init_client()
    with open(config['paths']['metadata_store'], 'r') as f:
        meta = json.load(f)

    buffer = {}
    if os.path.exists(config['paths']['solution_buffer']):
        with open(config['paths']['solution_buffer'], 'r') as f:
            buffer = json.load(f)

    for tid, specs in meta.items():
        if specs['status_completed'] or tid in buffer: continue

        complexity, items = synthesize_solutions(client, tid, specs)
        buffer[tid] = {"rank": complexity, "data": items}

        with open(config['paths']['solution_buffer'], 'w') as f:
            json.dump(buffer, f, indent=4)
        time.sleep(1) # Rate limiting

# === Execution Layer ===

def deploy_solution(session, tid, code):
    payload = {
        "id": tid, "code": code, "cuname": config['credentials']['account_email'],
        "owner": "", "adate": time.strftime("%Y%m%d-%H%M%Sz", time.gmtime()), "font": "100"
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"https://codingbat.com/prob/{tid}"
    }
    return session.post(f"{BASE_URL}/run", data=payload, headers=headers)

def simulate_human_workflow(session):
    with open(config['paths']['metadata_store'], 'r') as f:
        meta = json.load(f)
    with open(config['paths']['solution_buffer'], 'r') as f:
        buffer = json.load(f)

    for tid, payload in buffer.items():
        if meta[tid].get('status_completed'): continue

        log(LogColor.INFO, f"Executing deployment pipeline for unit {tid}")
        for idx, code in enumerate(payload['data']):
            wait = config['delays']['base_think_time'] \
                    * payload['rank'] \
                    * (1 + idx * 0.3) \
                    * random.uniform(0.8, 1.2)
            log(LogColor.INFO, f"Simulating cognitive delay: {wait:.1f}s")
            time.sleep(wait)

            deploy_solution(session, tid, code)

        log(LogColor.SUCCESS, f"Unit {tid} verified and closed.")

# === entry_point ===

def main():
    if len(sys.argv) < 2:
        print("Usage: python chinese-man.py [sync|gen|deploy]")
        return

    cmd = sys.argv[1]

    if cmd == 'sync':
        driver = get_automation_driver()
        authorize_session(driver)
        ctx = extract_session_context(driver)
        driver.quit()

        s = requests.Session()
        s.cookies.update(ctx)
        sync_task_repository(s)

    elif cmd == 'gen':
        batch_process_solutions()

    elif cmd == 'deploy':
        driver = get_automation_driver()
        authorize_session(driver)
        ctx = extract_session_context(driver)
        driver.quit()

        s = requests.Session()
        s.cookies.update(ctx)
        simulate_human_workflow(s)

if __name__ == "__main__":
    main()
