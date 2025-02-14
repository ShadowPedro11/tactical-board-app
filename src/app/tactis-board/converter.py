import csv
import json
from urllib.parse import urlparse

# Map team "slugs" to your team IDs
team_map = {
    "boavista": 222,
    "farense": 231,
    "est-amadora": 15130,
    "afs": 21595,
    "nacional": 225,
    "gil-vicente": 762,
    "fc-arouca": 240,
    "moreirense": 215,
    "rio-ave": 226,
    "fc-famalicao": 242,
    "estoril-praia": 230,
    "vitoria-sc": 224,
    "casa-pia-ac": 4716,
    "santa-clara": 227,
    "sc-braga": 217,
    "fc-porto": 212,
    "sporting": 228,
    "benfica": 211,
}

# Map CSV positions to the desired JSON keys.
# Adjust these if you need different keys.
position_map = {
    "Guarda Redes": "goalkeepes",
    "Defesa": "defesa",
    "Médio": "médio",
    "Avançado": "avançado"
}

def extract_team_name(url):
    """
    Given a URL like:
    "https://www.zerozero.pt/equipa/boavista/5?epoca_id=154"
    this function extracts "boavista" as the team slug.
    """
    parsed = urlparse(url)
    parts = parsed.path.split('/')
    # parts example: ['', 'equipa', 'boavista', '5']
    if len(parts) > 2:
        return parts[2]
    return None

# This dictionary will hold our final JSON data.
output = {}

with open("src/app/tactis-board/tugao.csv", newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        url = row["web-scraper-start-url"]
        team_slug = extract_team_name(url)
        if not team_slug:
            continue  # Skip rows with no valid team
        
        # Use your mapping to convert team slug to team ID.
        team_id = team_map.get(team_slug)
        if not team_id:
            # If the team isn't in your map, you might choose to skip or handle it differently.
            continue

        # Get the position label from the CSV and map it if needed.
        pos_label = row["position"]
        pos_key = position_map.get(pos_label, pos_label.lower())

        # Create team entry if it doesn't exist yet.
        if team_id not in output:
            output[team_id] = {"pos": {}}
        # Create the position group if it doesn't exist yet.
        if pos_key not in output[team_id]["pos"]:
            output[team_id]["pos"][pos_key] = []

        # Build the player dictionary using only the "number" and "name" fields.
        player = {"number": row["number"], "name": row["name"]}
        output[team_id]["pos"][pos_key].append(player)

# Write the JSON output to a file.
with open("players.json", "w", encoding="utf-8") as jsonfile:
    json.dump(output, jsonfile, ensure_ascii=False, indent=4)

print("Conversion complete! JSON file 'players.json' has been created.")
