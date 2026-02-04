from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup, NavigableString
from google import genai
import random
import requests
import tomllib
import json
import time
import sys
import os

with open('config.toml', 'rb') as f:
    config = tomllib.load(f)

base_url = 'https://codingbat.com'
java_url = 'https://codingbat.com/java'
login_url = 'https://codingbat.com/java'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

os.environ['GEMINI_API_KEY'] = config['gemini_api_key']


# === Utils ===

def setup_webdriver():
    sweetyfox_options = webdriver.FirefoxOptions()
    sweetyfox_options.add_argument('--headless')
    sweetyfox_options.add_argument('--no-sandbox')
    sweetyfox_options.add_argument('--disable-dev-shm-usage')

    return webdriver.Firefox(options=sweetyfox_options)


def login(driver):
    driver.get('https://codingbat.com/java')

    username_field = driver.find_element(By.NAME, 'uname')
    password_field = driver.find_element(By.NAME, 'pw')
    login_button = driver.find_element(By.NAME, 'dologin')

    username_field.send_keys(config['username'])
    password_field.send_keys(config['password'])
    login_button.click()

    time.sleep(config['login_sleep'])


def save_cookies(driver):
    cookies = driver.get_cookies()
    cookie_dict = {}
    for cookie in cookies:
        cookie_dict[cookie['name']] = cookie['value']
    return cookie_dict


# === Scrape ===

# Gathers all the tasks in codingbat.com
# with their status and saves to json
def scrape_tasks(session):
    response = session.get(java_url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')

    summs = soup.find_all('div', class_='summ')

    tasks = {}
    for summ in summs:
        category_link = summ.find('a')
        if not category_link:
            continue

        category_url = base_url + category_link.get('href')
        print(f"Scraping the category {category_url}...")

        category_tasks = scrape_category(session, category_url)
        tasks.update(category_tasks)

    with open(config['puppy_path'], 'w') as f:
        json.dump(tasks, f, indent=4, ensure_ascii=False)


def scrape_category(session, url):
    response = session.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')

    data = {}

    for td in soup.find_all('td'):
        link = td.find('a', href=True)
        img = td.find('img')

        if link and '/prob/p' in link['href']:
            task_id = link['href'].split('/')[-1]
            description, examples, signature = scrape_task_details(session, base_url + link['href'])
            done = 'c2' in (img['src'] if img else '')

            data[task_id] = {
                "description": description,
                "examples": examples,
                "signature": signature,
                "done": done
            }

    return data


def scrape_task_details(session, url):
    response = session.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')

    description_div = soup.find('div', class_='minh')

    if not description_div:
        return '', ''

    description = description_div.get_text(strip=True)
    examples = []
    signature = ''

    current = description_div.next_sibling
    while current:
        if current.name in ['p', 'form', 'button']:
            break
        if isinstance(current, NavigableString):
            text = current.strip()
            if '→' in text:
                examples.append(text)
        current = current.next_sibling

    ace_div = soup.find('div', id='ace_div')
    if ace_div:
        signature = ace_div.get_text().strip().split('\n')[0]

    return description, examples, signature


# === Generate Solutions ===

def gensols(client, task_data):
    base_tries = random.randint(config['lower_tries'], config['upper_tries'])
    response = client.models.generate_content(
        model = 'gemini-2.0-flash-lite',
        prompt = (
            "Act as a student learning Java. Analyze the problem complexity (1 to 3).\n"
            "1 - Easy (simple logic, 1-2 lines of code)\n"
            "2 - Medium (loops, multiple conditions, basic logic)\n"
            "3 - Hard (nested loops, complex data structures, algorithmic thinking)\n\n"

            "You will get:\n"
            "1. The Java problem description;\n"
            "2. The examples of input and expected output;\n"
            "3. The signature of the function.\n\n"

            f"Generate {base_tries}+<complexity_number>*{config['complexity_factor']} solutions where <tries_number>-1 solutions are incorrect and the last one is correct. "
            "Incorrect answers must have logical or syntax errors. "
            "Each version must be a slight improvement over the previous one, showing incremental progress.\n\n"

            "IMPORTANT RULES:\n"
            "- Output ONLY the complexity number and code.\n"
            "- Use 'EOS' as a plain text separator between solutions.\n"
            "- Do not use markdown backticks (```) or any conversational text.\n"
            "- Do not include any comments (like // Solution 1).\n"
            "- The provided signature already includes an opening brace '{'. Make sure your code completes the function correctly with a closing brace '}'.\n\n"

            "The format of the output must be exactly like this:\n"
            "<complexity_number>\n"
            "EOS\n"
            "<signature>\n"
            "   // your code here\n"
            "}\n"
            "EOS\n"
            "<signature>\n"
            "   // next version code\n"
            "}\n\n"

            f"The problem description:\n{task_data.get('description')}\n\n"
            f"The examples:\n{task_data.get('examples')}\n\n"
            f"The signature:\n{task_data.get('signature')}\n\n"
            f"The code style description:\n{config['code_style']}"
        )
    )
    parts = [p.strip() for p in response.text.split('EOS') if p.strip()]
    try:
        complexity = int(parts[0])
    except ValueError:
        complexity = 1
    solutions = parts[1:]

    return complexity, solutions


def lick_it(client):
    with open(config['puppy_path'], 'r', encoding='utf-8') as f:
        puppy = json.load(f)

    pussy = {}
    if os.path.exists(config['pussy_path']):
        with open(config['pussy_path'], 'r', encoding='utf-8') as f:
            pussy = json.load(f)

    for task_id, task_data in puppy.items():
        if task_data.get('done') or task_id in pussy:
            print(f"Skipping task {task_id}")
            continue
        print(f"Generating solutions for {task_id}")
        complexity, solutions = gensols(client, task_data)
        pussy[task_id] = {
            "complexity": complexity,
            "solutions": solutions
        }

        with open(config['pussy_path'], 'w', encoding='utf-8') as f:
            json.dump(pussy, f, indent=4, ensure_ascii=False)


# === Suck ma dick ===

def mark_as_done(task_id):
    try:
        with open(config['puppy_path'], 'r', encoding='utf-8') as f:
            puppy = json.load(f)

        if task_id in puppy:
            puppy[task_id]['done'] = True
        else:
            return

        with open(config['puppy_path'], 'w', encoding='utf-8') as f:
            json.dump(puppy, f, indent=4, ensure_ascii=False)

    except Exception as e:
        print(f"Failed to mark as done: {e}")


def submit_solution(session, task_id, code):
    payload = {
        "id": task_id,
        "code": code,
        "cuname": config['username'],
        "owner": "",
        "adate": time.strftime("%Y%m%d-%H%M%Sz", time.gmtime()),
        "font": "100"
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"[https://codingbat.com/prob/](https://codingbat.com/prob/){task_id}"
    }

    response = session.post("[https://codingbat.com/run](https://codingbat.com/run)", data=payload, headers=headers)
    return response.text


def how_much_is_the_fish(complexity, attempt_number):
    base_time = config['base_time'] * complexity
    progress_factor = 1 + (attempt_number * 0.2)
    jitter = random.uniform(0.8, 1.2)

    wait_time = base_time * progress_factor * jitter

    print(f"Thinking for {wait_time:.1f} seconds (Attempt {attempt_number + 1})...")
    time.sleep(wait_time)


def crack_the_nut(session, task_id, solution_data):
    complexity = solution_data['complexity']
    solutions = solution_data['solutions']
    for i, code in enumerate(solutions):
        how_much_is_the_fish(complexity, i)
        submit_solution(session, task_id, code)


def crack_all_nuts(session):
    with open(config['puppy_path'], 'r', encoding='utf-8') as f:
        puppy = json.load(f)

    with open(config['pussy_path'], 'r', encoding='utf-8') as f:
        pussy = json.load(f)

    for task_id, solution_data in pussy.items():
        if puppy[task_id].get('done'):
            print(f"Skipping task {task_id}")
            continue
        print(f"Cracking the task {task_id}...")
        crack_the_nut(session, task_id, solution_data)
        mark_as_done(task_id)


# === Come over here! ===

def main():
    args = sys.argv
    if len(args) == 1:
        print(f"No commands specified. Options: puppy|pussy|omnomnom.")
    elif len(args) > 2:
        print(f"Too many arguments.")
    elif args[1] == 'puppy':
        try:
            driver = setup_webdriver()
            login(driver)
            cookies = save_cookies(driver)

            session = requests.Session()
            session.cookies.update(cookies)

            scrape_tasks(session)
        except Exception as e:
            print(f"something went wrong: {e}")
        finally:
            driver.quit()
    elif args[1] == 'pussy':
        if not os.path.exists(config['puppy_path']):
            print(f"No task config found.")
            return
        try:
            client = genai.Client()
            lick_it(client)
        except Exception as e:
            print(f"something went wrong: {e}")
    elif args[1] == 'omnomnom':
        if not os.path.exists(config['puppy_path']) or not os.path.exists(config['pussy_path']):
            print(f"No task and/or solutions config files found.")
            return
        try:
            driver = setup_webdriver()
            login(driver)
            cookies = save_cookies(driver)

            session = requests.Session()
            session.cookies.update(cookies)

            crack_all_nuts(session)
        except Exception as e:
            print(f"something went wrong: {e}")
        finally:
            driver.quit()
    elif args[1] == 'easter-egg':
        print(f"You found it! 🥚")
    else:
        print(f"No argument found: {args[1]}")


if __name__ == "__main__":
    main()
