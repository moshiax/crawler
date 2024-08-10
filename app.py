from flask import Flask, render_template, jsonify
import json
from collections import defaultdict
import os
from urllib.parse import urlparse
import geoip2.database

app = Flask(__name__)


VISITED_FILE = 'visited_links.json'
GEOIP_DB = 'GeoLite2-City.mmdb'


geoip_reader = geoip2.database.Reader(GEOIP_DB)

def load_data():

    if not os.path.exists(VISITED_FILE):
        return []
    
    data = []
    try:
        with open(VISITED_FILE, 'r', encoding='utf-8') as file:
            json_data = json.load(file)
            for entry in json_data:
                try:

                    json.dumps(entry)
                    data.append(entry)
                except (TypeError, ValueError) as e:
                    print(f"Skipping invalid JSON entry: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from file {VISITED_FILE}: {e}")

        with open(VISITED_FILE, 'r', encoding='utf-8') as file:
            json_data = file.readlines()
            for line in json_data:
                try:
                    entry = json.loads(line.strip())
                    json.dumps(entry)
                    data.append(entry)
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    print(f"Skipping invalid line: {e}")
    except Exception as e:
        print(f"Error loading data from file {VISITED_FILE}: {e}")
    return data

def get_similar_ip_location(ip):

    ip_parts = ip.split('.')
    for i in range(1, 256):
        modified_ip = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.{i}"
        try:
            response = geoip_reader.city(modified_ip)
            lat = response.location.latitude
            lon = response.location.longitude
            if lat is not None and lon is not None:
                print(f"Found similar IP location for {modified_ip}: lat={lat}, lon={lon}")
                return lat, lon
        except geoip2.errors.AddressNotFoundError:
            continue
        except Exception as e:
            print(f"Error getting location for IP {modified_ip}: {e}")
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

    data = load_data()
    clusters = generate_clusters(data)
    return render_template('index.html', clusters=clusters)

@app.route('/map')
def map_view():

    data = load_data()
    clusters = generate_clusters(data)
    return render_template('map.html', clusters=clusters)

@app.route('/data')
def data():

    return jsonify(generate_clusters(load_data()))

if __name__ == '__main__':
    app.run(debug=True)
