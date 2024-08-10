import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import socket
import re
import json
import argparse
from colorama import Fore, init

init(autoreset=True)

visited_file = "visited_links.json"
max_connections = 10
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://www.google.com/'
}

def load_visited():
    try:
        with open(visited_file, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return []

def save_visited(visited):
    with open(visited_file, "w", encoding="utf-8") as file:
        json.dump(visited, file, ensure_ascii=False, indent=4)

def valid_url(url):
    return re.match(r'^https?://', url) is not None

def get_ip(domain):
    try:
        if is_valid_domain(domain):
            ip = socket.gethostbyname(domain)
            return ip
        else:
            return None
    except socket.gaierror as e:
        return None

def extract_ip_from_url(url):
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain and is_valid_domain(domain):
            ip = socket.gethostbyname(domain)
            return ip
        else:
            return None
    except (socket.gaierror, TypeError) as e:
        return None

def is_excluded_url(url):
    excluded_prefixes = [
        'tel:', 'mailto:', 'tg:', 'whatsapp:', 'fb:', 'viber:', 'skype:', 'zoommtg:',
        'slack:', 'snapchat:', 'line:', 'weixin:', 'wechat:', 'instagram:', 'twitter:',
        'pinterest:', 'linkedin:', 'youtube:', 'spotify:', 'messenger:', 'tiktok:',
        'discord:', 'signal:', 'telegram:', 'googlemeet:', 'teams:', 'webex:',
        'facetime:', 'msteams:', 'meetup:', 'venmo:', 'paypal:', 'cashapp:',
        'alipay:', 'googlepay:', 'applepay:', 'waze:', 'uber:', 'lyft:', 'zelle:', 
        'about:', 'ms-windows-store:', 'javascript:void(0)', '#', 'fax:',
    ]
    
    excluded_domains = ['store.microsoft.com']
    
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if any(url.startswith(prefix) for prefix in excluded_prefixes):
        return True
    if any(domain in parsed_url.netloc for domain in excluded_domains):
        return True
    if domain.count('.') == 0:
        return True
    
    return False

async def fetch(session, url):
    try:
        print(Fore.YELLOW + f"Fetching {url}")
        async with session.get(url, headers=headers, verify_ssl=False) as response:
            print(Fore.GREEN + f"Status code for {url}: {response.status}")
            content_type = response.headers.get('Content-Type', '')
            if response.status == 200:
                text = await response.text()
                return text, str(response.url), content_type
            else:
                print(Fore.RED + f"Failed to access {url} with status code {response.status}")
                return None, None, content_type
    except Exception as e:
        print(Fore.RED + f"Error fetching {url}: {e}")
        return None, None, None

async def check_alive(url):
    return True
def update_ip_entry(ip, title, url, visited, depth, parent_ip=None):

    if not any(entry['ip'] == ip for entry in visited):

        visited.append({
            "ip": ip,
            "title": title,
            "url": url,
            "depth": depth,
            "parent_ip": parent_ip,
            "scanned": True
        })

async def crawl(session, url, visited, depth=0, parent_ip=None):
    if is_excluded_url(url):
        return

    if url.endswith('.js'):
        print(Fore.CYAN + f"Skipping JS file: {url}")
        return

    print(Fore.YELLOW + f"Crawling {url} at depth {depth}")

    parsed_url = urlparse(url)
    domain = parsed_url.netloc or parsed_url.path
    if domain.startswith("www."):
        domain = domain[4:]

    try:
        if not is_valid_domain(domain):
            print(Fore.RED + f"Invalid domain: {domain}")
            return

        ip = get_ip(domain)
        if ip is None:
            ip = extract_ip_from_url(url)

        if not await check_alive(url):
            print(Fore.RED + f"URL {url} is not accessible.")
            return

        if depth == 0 and ip:
            update_ip_entry(ip, "", url, visited, depth, parent_ip)
            save_visited(visited)

        text, full_url, content_type = await fetch(session, url)
        if text is None:
            print(Fore.RED + f"Failed to fetch {url}. Skipping...")
            return

        soup = BeautifulSoup(text, 'lxml' if 'xml' in content_type else 'html.parser')
        title = soup.title.string if soup.title else ""

        if not ip:
            print(Fore.RED + f"Invalid IP for {url}. Skipping adding to visited.")
        else:
            if title:
                update_ip_entry(ip, title, full_url, visited, depth, parent_ip)
                save_visited(visited)

        tasks = []

        for link in soup.find_all('a', href=True):
            new_url = link['href']
            if not valid_url(new_url):
                new_url = urljoin(url, new_url)
            if not any(entry['url'] == new_url for entry in visited):
                tasks.append(crawl(session, new_url, visited, depth + 1, ip))


        for tag in soup.find_all('link'):
            if tag.get('href') and 'stylesheet' in tag.get('rel', []):
                file_url = urljoin(url, tag['href'])
                if valid_url(file_url) and not any(entry['url'] == file_url for entry in visited):
                    tasks.append(crawl(session, file_url, visited, depth + 1, ip))

        await asyncio.gather(*tasks)

    except Exception as e:
        print(Fore.RED + f"Error processing URL {url}: {e}")



def is_valid_domain(domain):
    try:
        return len(domain) < 253 and all(len(label) < 63 for label in domain.split('.'))
    except Exception as e:
        print(Fore.RED + f"Error validating domain: {e}")
        return False

async def main(start_url):
    visited = load_visited()
    if not visited:
        save_visited([])
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit_per_host=max_connections)) as session:
        await crawl(session, start_url, visited)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Asynchronous web crawler")
    parser.add_argument("url", help="The start URL to crawl")
    args = parser.parse_args()

    start_url = args.url
    asyncio.run(main(start_url))
