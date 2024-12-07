import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import socket
import re
import json
import argparse
from colorama import Fore, init
import lxml
import os

init(autoreset=True)

visited_file = "visited_links.json"
excluded_file = "excluded_links.json"

max_connections = 10
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://www.google.com/'
}

def load_visited():
    visited = []
    try:
        with open(visited_file, "r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    visited.append(json.loads(line.strip()))
    except FileNotFoundError:
        pass
    return visited


def get_ip(domain):
    try:
        if is_valid_domain(domain):
            ip = socket.gethostbyname(domain)
            return ip
        else:
            return None
    except socket.gaierror:
        return None

def extract_ip_from_url(url):
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain and is_valid_domain(domain):
            return socket.gethostbyname(domain)
        return None
    except (socket.gaierror, TypeError):
        return None

logged_urls = set()

def load_logged_urls():
    try:
        with open(excluded_file, "r", encoding="utf-8") as file:
            return {line.strip() for line in file}
    except FileNotFoundError:
        return set()

logged_urls = load_logged_urls()

loggable_extensions = ['.zip', '.rar', '.tar.gz', '.7z', '.exe', '.msi', '.apk', '.db', '.sql', '.mp4', 'pdf', '.avi', '.mkv']
excluded_extensions = [
    '.png', '.jpg', '.webp', '.jpeg', '.gif', '.ico', '.svg',
    '.woff', '.woff2', '.ttf', '.eot', '.db', '.sql', '.mp3',
    '.iso', '.flv', '.mov', '.wav', '.flac',
    '.ogg', '.bmp', '.psd', '.ai', '.eps', '.docx', '.xlsx',
    '.pptx', '.epub', '.mobi', '.chm', '.swf',
    '.tar', '.gz', '.bz2', '.xz', '.dmg', '.pkg', '.bat',
    '.msi', '.vhd', '.vmdk', '.ova', '.iso', '.img'
]


def log_excluded_url(url):
    parsed_url = urlparse(url)
    path = parsed_url.path
    extension = next((ext for ext in excluded_extensions if path.endswith(ext)), "unknown")
    entry = json.dumps({extension: url}, ensure_ascii=False)
    
    if entry not in logged_urls:
        with open(excluded_file, "a", encoding="utf-8") as file:
            file.write(entry + "\n")
        logged_urls.add(entry)

excluded_domains = ['store.microsoft.com']

def is_excluded_url(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    path = parsed_url.path

    if ":" in url:
        if parsed_url.scheme and parsed_url.scheme not in ['http', 'https']:
            return True

        if ":" in domain:
            parts = domain.split(":")
            if len(parts) == 2 and not parts[1].isdigit():
                return True

    if any(domain in parsed_url.netloc for domain in excluded_domains):
        return True
    if domain.count('.') == 0:
        return True

    if any(path.endswith(ext) for ext in excluded_extensions):
        if any(path.endswith(ext) for ext in loggable_extensions):
            log_excluded_url(url)
        return True

    return False

def clear_cache():
    if os.path.exists(visited_file):
        os.remove(visited_file)
    if os.path.exists(excluded_file):
        os.remove(excluded_file)

async def fetch(session, url):
    try:
    #    print(Fore.YELLOW + f"Fetching {url}")
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

def is_js_file(url): return url.endswith('.js') if url else False

def clean_title(title): return ' '.join(title.split()).strip() if title else ""

def update_ip_entry(ip, title, url, visited, depth, parent_ip=None):
    if parent_ip:
        parent_entry = next((entry for entry in visited if entry['ip'] == parent_ip), None)
        if parent_entry:
            depth = parent_entry['depth'] + 1

    clean_title_text = clean_title(title)

    if not any(entry['ip'] == ip for entry in visited):
        new_entry = {
            "ip": ip,
            "title": clean_title_text,
            "url": url,
            "depth": depth,
            "parent_ip": parent_ip,
            "scanned": True
        }
        visited.append(new_entry)

        with open(visited_file, "a", encoding="utf-8") as file:
            json.dump(new_entry, file, ensure_ascii=False)
            file.write("\n")

def is_valid_domain(domain): return len(domain) < 253 and all(len(label) < 63 for label in domain.split('.'))

def extract_links_from_js(js_content):
    pattern = r'(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s\'"]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s\'"]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s\'"]{2,}|www\.[a-zA-Z0-9]+\.[^\s\'"]{2,}|[a-zA-Z0-9][a-zA-Z0-9-]+\.[^\s\'"]{2,})|((?<=href=").*?(?="))'
    return re.findall(pattern, js_content, re.IGNORECASE)
    
    
def valid_url(url):
    return re.match(r'^https?://', url) is not None

successful_crawls = 0

async def crawl(session, url, visited, depth=1, max_depth=float('inf'), parent_ip=None):
    global successful_crawls  
    if depth > max_depth:
        return
    
    if is_excluded_url(url):
        return

    parsed_url = urlparse(url)
    domain = parsed_url.netloc or parsed_url.path
    if domain.startswith("www."):
        domain = domain[4:]

    try:
        if not is_valid_domain(domain):
            print(Fore.RED + f"Invalid domain: {domain}")
            return

        ip = get_ip(domain) or extract_ip_from_url(url)

        text, full_url, content_type = await fetch(session, url)
        if text is None:
            print(Fore.RED + f"Failed to fetch {url}. Skipping...")
            return

        if is_js_file(url):
            links = extract_links_from_js(text)
            tasks = [crawl(session, link, visited, depth + 1, max_depth, ip) for link in links if not any(entry['url'] == link for entry in visited)]
            await asyncio.gather(*tasks)
            return

        soup = BeautifulSoup(text, 'xml' if 'xml' in content_type else 'lxml')
        title = soup.title.string if soup.title else ""

        if ip:
            update_ip_entry(ip, title, full_url, visited, depth, parent_ip)

        pattern = r'(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s\'"]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s\'"]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s\'"]{2,}|www\.[a-zA-Z0-9]+\.[^\s\'"]{2,})|((?<=href=").*?(?="))'

        links = re.findall(pattern, text)

        tasks = []
        for link in links:
            new_url = link[0] if link[0] else link[1]
            new_url = re.sub(r'\);--.*$', '', new_url)
            if not valid_url(new_url):
                new_url = urljoin(url, new_url)
            if not any(entry['url'] == new_url for entry in visited):
                tasks.append(crawl(session, new_url, visited, depth + 1, max_depth, ip))

        successful_crawls += 1

        await asyncio.gather(*tasks)

    except Exception as e:
        print(Fore.RED + f"Error crawling {url}: {e}")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Domain to start crawling (e.g., pornhub.com)")
    parser.add_argument("max_depth", type=int, help="Maximum crawling depth")
    args = parser.parse_args()

    clear_cache()  

    url = "https://" + args.url if not args.url.startswith("http") else args.url
    max_depth = args.max_depth + 1

    visited = load_visited()
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=max_connections)) as session:
        await crawl(session, url, visited, max_depth=max_depth)

    print(Fore.CYAN + f"Total successful crawls: {successful_crawls}")

if __name__ == "__main__":
    asyncio.run(main())
