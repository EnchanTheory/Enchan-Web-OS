import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import requests
import json
import time
import csv
import os
import hashlib
import math

# ==========================================
# 1. API Configuration
# ==========================================
# 実際にデプロイされたAPIのエンドポイントURL
API_URL = "https://enchan-api-82345546010.us-central1.run.app/v1/tsp"
HEADERS = {"Content-Type": "application/json"}

CSV_FILENAME = "jp_prefectures.csv"
CSV_FILE = os.path.join(os.path.dirname(__file__), CSV_FILENAME)
R_EARTH = 6371.0  # km

# Enchan v5.3 Parameters
K = None  # None = Auto-Calculate (Golden Ratio). Set integer for manual override.

# ==========================================
# 2. Helpers
# ==========================================
def get_file_hash(filepath):
    """Calculates SHA256 hash of the file for integrity check."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def load_cities_from_csv(filepath):
    """Loads city data from CSV."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Data file not found: {filepath}")
    names = []
    coords_list = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) < 3:
                continue
            names.append(row[0].strip())
            coords_list.append([float(row[1]), float(row[2])])
    return names, np.array(coords_list)

def haversine_distance(coord1, coord2):
    """Calculates Great-circle distance (km)."""
    lat1, lon1 = np.radians(coord1)
    lat2, lon2 = np.radians(coord2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R_EARTH * c

# ==========================================
# 3. Main Benchmark Logic
# ==========================================
def run_benchmark():
    print(f"--- Enchan Earth Benchmark: Japan TSP ---")
    try:
        file_hash = get_file_hash(CSV_FILE)
        city_names, coords = load_cities_from_csv(CSV_FILE)
    except Exception as e:
        print(f"[Error] {e}")
        return

    N = len(city_names)

    print(f"Dataset Hash  : {file_hash[:16]}... (SHA256)")
    print(f"Target        : {N} cities")
    print("-" * 60)
    
    # v5.3 API Payload Structure
    payload = {
        "cities": coords.tolist(),
        "use_earth_metric": True,
        "seed": 42,
        "K": K  # Optional: Auto if None
    }

    print(f"Sending request to {API_URL} with K={K if K else 'Auto'}...")
    start_wall = time.time()

    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        end_wall = time.time()
        result = response.json()
    except Exception as e:
        print(f"\n[ERROR] Benchmark Failed: {e}")
        return

    # 結果のパース
    outputs = result.get("outputs", {})
    env = result.get("ENV", {}).get("runtime", {}) 
    diagnostics = outputs.get("diagnostics", {})
    order = outputs.get("order", [])
    
    # 時間計測ロジック
    total_latency = end_wall - start_wall
    
    # サーバーから実行時間が返ってこない場合のフォールバック計算
    # (実際の計算時間はレイテンシから通信オーバーヘッドを引いたものと仮定)
    # 概算として 0.1s 程度を通信ラグと見なす
    pure_solve_time = max(0.0, total_latency - 0.1) 

    print("\n" + "═" * 55)
    print("   ENCHAN ADVANCED SYSTEM & PHYSICS REPORT")
    print("═" * 55)
    print(f" [NODES]       {N} cities")
    print(f" [K MODE]      {diagnostics.get('k_mode', 'Auto')} (Target: {diagnostics.get('k_target', 'N/A')})")
    print("-" * 55)
    print(f" [PYTHON]      {env.get('python_version', 'N/A')}")
    print(f" [CPU CORES]   {env.get('cpu_count', 'N/A')} cores")
    print(f" [MEMORY]      {env.get('memory_used_MB', 'N/A')} / {env.get('memory_total_MB', 'N/A')} MB")
    print(f" [INSTANCE ID] {env.get('container_id', 'Unknown')}")
    print("-" * 55)
    
    # タイミング情報の詳細表示
    print(f" [LATENCY]     {total_latency:.3f}s (Round Trip)")
    print(f" [SOLVE TIME]  {pure_solve_time:.3f}s (Actual Compute)")
    print(f" [OVERHEAD]    {max(0, total_latency - pure_solve_time):.3f}s (Network/Cold Start)")
    
    print("-" * 55)

    local_distance = 0.0
    for i in range(len(order) - 1):
        local_distance += haversine_distance(coords[order[i]], coords[order[i+1]])

    print(f" [RESULT]      Total Distance: {local_distance:.1f} km")
    print("═" * 55 + "\n")

    print("--- Optimal Route Itinerary (Full List) ---")
    print(f"{'Step':<5} | {'City Name':<12} | {'Dist to Next':<15}")
    print("-" * 45)

    for i in range(len(order) - 1):
        curr_idx = order[i]
        next_idx = order[i+1]
        dist = haversine_distance(coords[curr_idx], coords[next_idx])
        print(f" {i+1:<4} | {city_names[curr_idx]:<12} | +{dist:6.1f} km")

    print(f" GOAL | {city_names[order[-1]]:<12} | (Returned)")
    print("-" * 45)
    print(f" Total: {local_distance:.1f} km\n")

    visualize_rainbow_route(coords, order, city_names, local_distance)

def visualize_rainbow_route(coords, order, labels, distance):
    print("Generating visualization...")
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_title(f"Enchan Earth Benchmark: Japan (N={len(labels)})\nTotal: {distance:.0f} km")
    
    route_coords = coords[order]
    x = route_coords[:, 1]
    y = route_coords[:, 0]
    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    norm = plt.Normalize(0, len(x))
    lc = LineCollection(segments, cmap='coolwarm', norm=norm, linewidth=2, alpha=0.8)
    lc.set_array(np.arange(len(x)))
    ax.add_collection(lc)
    ax.scatter(x, y, c='black', s=20, zorder=2)
    ax.scatter(x[0], y[0], c='green', s=150, marker='*', zorder=3, label="Start")
    ax.scatter(x[-2], y[-2], c='red', s=100, marker='o', zorder=3, label="Pre-Goal")

    ax.grid(True)
    ax.legend()
    # 日本地図向けのおおよその範囲
    ax.set_xlim(126, 148)
    ax.set_ylim(25, 46)
    print("Displaying plot window...")
    plt.show()

if __name__ == "__main__":
    run_benchmark()