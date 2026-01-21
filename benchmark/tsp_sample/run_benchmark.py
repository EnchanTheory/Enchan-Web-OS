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

# ==============================================================================
# 1. GLOBAL CONFIGURATION
# ==============================================================================
API_URL = "https://enchan-api-82345546010.us-central1.run.app/v1/tsp"
HEADERS = {"Content-Type": "application/json"}

CSV_FILENAME = "jp_prefectures.csv"
CSV_FILE = os.path.join(os.path.dirname(__file__), CSV_FILENAME)
R_EARTH = 6371.0  # Earth radius in km

# Enchan v5.3 Solver Parameters
# K: Golden Ratio base resonance. Set to None for automatic optimization.
K = None 

# ==============================================================================
# 2. CORE UTILITIES
# ==============================================================================
def get_file_hash(filepath):
    """Integrity check: returns SHA256 hash of the dataset."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def load_cities_from_csv(filepath):
    """Loads geospatial coordinates from CSV."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Missing dataset: {filepath}")
    names, coords_list = [], []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            if len(row) < 3: continue
            names.append(row[0].strip())
            coords_list.append([float(row[1]), float(row[2])])
    return names, np.array(coords_list)

def haversine_distance(coord1, coord2):
    """Calculates geodesic distance between two points."""
    lat1, lon1 = np.radians(coord1)
    lat2, lon2 = np.radians(coord2)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2)**2
    return R_EARTH * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

# ==============================================================================
# 3. BENCHMARK EXECUTION
# ==============================================================================
def run_benchmark():
    """Executes the Enchan Earth TSP Benchmark."""
    print(f"--- Enchan Earth Benchmark: Japan TSP ---")
    try:
        file_hash = get_file_hash(CSV_FILE)
        city_names, coords = load_cities_from_csv(CSV_FILE)
    except Exception as e:
        print(f"[Critical Error] Failed to initialize: {e}")
        return

    N = len(city_names)
    print(f"Dataset Hash : {file_hash[:16]}... (SHA256)")
    print(f"Nodes        : {N} locations")
    print("-" * 60)
    
    payload = {
        "cities": coords.tolist(),
        "use_earth_metric": False,
        "seed": 314,
        "K": K,
        "industrial_strict": True,
        "use_2opt": True
    }

    print(f"Requesting Solution from {API_URL}...")
    start_wall = time.time()

    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        end_wall = time.time()
        result = response.json()
    except Exception as e:
        print(f"\n[API ERROR] Transmission failed: {e}")
        return

    # Data Extraction
    outputs = result.get("outputs", {})
    env = result.get("ENV", {}).get("runtime", {}) 
    diagnostics = outputs.get("diagnostics", {})
    order = outputs.get("order", [])
    
    # Precise Timing Analysis
    total_latency = end_wall - start_wall
    pure_solve_time = result.get("TIMING", {}).get("total_wall_time", 0.0)
    internal_solve_trace = diagnostics.get("solve_time")

    # ARTIFACT REPORT
    print("\n" + "═" * 55)
    print("   ENCHAN ADVANCED SYSTEM & PHYSICS REPORT")
    print("═" * 55)
    print(f" [NODES]       {N} cities")
    print(f" [K MODE]      {diagnostics.get('k_mode', 'Auto')} (Target: {diagnostics.get('k_target', 'N/A')})")
    print("-" * 55)
    print(f" [PYTHON]      {env.get('python_version', 'N/A')}")
    print(f" [CPU CORES]   {env.get('cpu_count', 'N/A')} cores")
    print(f" [MEMORY]      {env.get('memory_used_MB', 'N/A')} / {env.get('memory_total_MB', 'N/A')} MB")
    print("-" * 55)
    
    print(f" [LATENCY]     {total_latency:.3f}s (Round Trip)")
    
    if pure_solve_time is not None and pure_solve_time > 0:
        overhead = total_latency - pure_solve_time
        efficiency = (pure_solve_time / total_latency * 100)
        print(f" [SOLVE TIME]  {pure_solve_time:.3f}s (Server Wall Time)")
        print(f" [OVERHEAD]    {overhead:.3f}s (Network/Cloud Latency)")
        print(f" [EFFICIENCY]  {efficiency:.1f}%")
    else:
        print(f" [SOLVE TIME]  Unknown (Not reported by API)")
        print(f" [OVERHEAD]    {total_latency:.3f}s (Total Latency as proxy)")

    if internal_solve_trace:
        print(f" [TRACE]       Internal engine trace: {internal_solve_trace:.3f}s")

    print("-" * 55)

    # Path Verification
    local_distance = 0.0
    for i in range(len(order) - 1):
        local_distance += haversine_distance(coords[order[i]], coords[order[i+1]])

    print(f" [RESULT]      Total Path Distance: {local_distance:.1f} km")
    print("═" * 55 + "\n")

    # Itinerary Output
    print("--- Optimal Route Itinerary ---")
    print(f"{'Step':<5} | {'City Name':<12} | {'Leg Dist'}")
    print("-" * 35)
    for i in range(len(order) - 1):
        d = haversine_distance(coords[order[i]], coords[order[i+1]])
        print(f" {i+1:<4} | {city_names[order[i]]:<12} | +{d:6.1f} km")
    print(f" GOAL  | {city_names[order[-1]]:<12} | (Terminus)")
    print("-" * 35 + "\n")

    visualize_rainbow_route(coords, order, city_names, local_distance)

def visualize_rainbow_route(coords, order, labels, distance):
    """Renders the optimized route using a rainbow gradient."""
    print("Initializing Geospatial Visualization...")
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_title(f"Enchan Earth: Optimized Route (N={len(labels)})\nTotal Distance: {distance:.0f} km", fontsize=12)
    
    route_coords = coords[order]
    x, y = route_coords[:, 1], route_coords[:, 0]
    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    
    lc = LineCollection(segments, cmap='coolwarm', norm=plt.Normalize(0, len(x)), linewidth=2, alpha=0.8)
    lc.set_array(np.arange(len(x)))
    ax.add_collection(lc)
    
    ax.scatter(x, y, c='black', s=20, zorder=2)
    ax.scatter(x[0], y[0], c='green', s=150, marker='*', zorder=3, label="Start")
    
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.legend()
    ax.set_xlim(126, 148); ax.set_ylim(25, 46) # Japan Geographic Frame
    plt.show()

if __name__ == "__main__":
    run_benchmark()