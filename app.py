from flask import Flask, render_template, jsonify, send_file, request
import json
from collections import defaultdict
import os
from urllib.parse import urlparse
import geoip2.database
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

app = Flask(__name__)

VISITED_FILE = 'visited_links.json'
GEOIP_DB = 'GeoLite2-City.mmdb'
geoip_reader = geoip2.database.Reader(GEOIP_DB)

global_data = []



EXCLUDED_FILE = 'excluded_links.json'

def load_excluded_files():
    if not os.path.exists(EXCLUDED_FILE):
        return []
    try:
        files = []
        with open(EXCLUDED_FILE, 'r', encoding='utf-8') as file:
            for line in file:
                try:
                    data = json.loads(line.strip())
                    for ext, url in data.items():
                        files.append({"extension": ext, "url": url})
                except json.JSONDecodeError as e:
                    print(f"e: {line}. {e}")
        return files
    except Exception as e:
        print(f"e {EXCLUDED_FILE}: {e}")
        return []

@app.route('/files')
def files():
    files_data = load_excluded_files()
    return render_template('files.html', files=files_data)


class FileChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path == os.path.abspath(VISITED_FILE):
            update_data()

    def on_deleted(self, event):
        if event.src_path == os.path.abspath(VISITED_FILE):
            clear_data()

def load_initial_data():
    global global_data
    if not os.path.exists(VISITED_FILE):
        return
    
    try:
        with open(VISITED_FILE, 'r', encoding='utf-8') as file:
            content = file.read().strip()
            if not content:
                print(f"{VISITED_FILE} empty.")
                return
            global_data = []
            for line in content.splitlines():
                try:
                    entry = json.loads(line)
                    global_data.append(entry)
                except json.JSONDecodeError as e:
                    print(f"e json: {line}\n {e}")
    except Exception as e:
        print(f"{VISITED_FILE}: {e}")

def update_data():
    """Обновляет глобальные данные, отслеживая добавление или удаление строк."""
    global global_data
    if not os.path.exists(VISITED_FILE):
        clear_data()
        return

    try:
        with open(VISITED_FILE, 'r', encoding='utf-8') as file:
            content = file.read().strip()
            if not content:
                print(f"{VISITED_FILE} empty.")
                return
            new_data = []
            for line in content.splitlines():
                try:
                    entry = json.loads(line)
                    new_data.append(entry)
                except json.JSONDecodeError as e:
                    print(f"e: {line}\n {e}")
        existing_urls = {entry['url'] for entry in global_data}
        new_urls = {entry['url'] for entry in new_data}
        urls_to_remove = existing_urls - new_urls
        global_data = [entry for entry in global_data if entry['url'] not in urls_to_remove]

        for entry in new_data:
            if entry['url'] not in existing_urls:
                global_data.append(entry)

    except Exception as e:
        print(f"e {VISITED_FILE}: {e}")

def clear_data():
    global global_data
    global_data = []
    print(f"cleared.")

def get_similar_ip_location(ip):
    ip_parts = ip.split('.')
    for i in range(1, 256):
        modified_ip = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.{i}"
        try:
            response = geoip_reader.city(modified_ip)
            lat = response.location.latitude
            lon = response.location.longitude
            if lat is not None and lon is not None:
                print(f"Chosen near for {modified_ip}: lat={lat}, lon={lon}")
                return lat, lon
        except geoip2.errors.AddressNotFoundError:
            continue
        except Exception as e:
            print(f"e {modified_ip}: {e}")
            continue
    return None, None

def get_location(ip):
    try:
        response = geoip_reader.city(ip)
        lat = response.location.latitude
        lon = response.location.longitude
        if lat is None or lon is None:
            lat, lon = get_similar_ip_location(ip)
            if lat is None or lon is None:
                lat, lon = 55.751244, 37.618423  
        return lat, lon
    except geoip2.errors.AddressNotFoundError:
        lat, lon = get_similar_ip_location(ip)
        if lat is None or lon is None:
            lat, lon = 55.751244, 37.618423 
        return lat, lon
    except Exception as e:
        return 55.751244, 37.618423

def generate_clusters(data):
    clusters = defaultdict(list)
    for entry in data:
        url = entry.get('url', '')
        ip = entry.get('ip', '')
        title = entry.get('title', '')
        parent_ip = entry.get('parent_ip', '')  
        domain = urlparse(url).netloc
        lat, lon = get_location(ip)
        depth = entry.get('depth', 0)  
        clusters[ip].append({
            'url': url,
            'title': title,
            'lat': lat,
            'lon': lon,
            'depth': depth,
            'parent_ip': parent_ip 
        })
    return clusters

@app.route('/')
def index():
    return render_template('index.html', clusters=generate_clusters(global_data))

@app.route('/data')
def data():
    return jsonify(generate_clusters(global_data))

if __name__ == "__main__":
    load_initial_data()
    event_handler = FileChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(os.path.abspath(VISITED_FILE)), recursive=False)
    observer.start()
    try:
        app.run(debug=True)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
