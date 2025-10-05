"""
Bot Phoenix - Automatisation de la quête Act 2-1 de Nostale
Avec système de cache intelligent pour les appels NosHydra

Ce script utilise:
- Phoenix API pour contrôler le personnage
- NosHydra API avec cache local
- Fichiers JSON locaux pour les données de jeu
"""

import json
import time
import requests
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from phoenixapi.finder import create_api_from_name
from phoenixapi.api import PhoenixApi

# =====================================================
# CONFIGURATION
# =====================================================

CHARACTER_NAME = "Khaliste"  # À MODIFIER

# Chemins vers vos fichiers JSON locaux
DATA_PATH = Path("./data")
MAPS_FOLDER = DATA_PATH / "maps"  # Dossier contenant c_map_1.json à c_map_412.json
CACHE_FOLDER = DATA_PATH / "cache"  # Cache pour les appels NosHydra

# Fichiers de données
NPCS_JSON = DATA_PATH / "monsters.json"
MONSTERS_JSON = DATA_PATH / "monsters.json"
MAPS_JSON = DATA_PATH / "maps.json"

# Configuration NosHydra
NOSHYDRA_BASE_URL = "https://www.noshydra.com"

# Cookie Cloudflare - À mettre à jour toutes les 10-20 minutes
# Récupérez-le depuis votre navigateur (F12 > Application > Cookies > cf_clearance)
CF_CLEARANCE_COOKIE = "UjdTF8MmqdFy38WV2q6q6VKbetJ4tC7jB82imoChX88-1759666280-1.2.1.1-MgVrVeCjClMacKkZvRGFiod1qtsSaP5pBBAFIyTHXdT75vKBBsJSiCSzrW4Z_NWpeokLAqSDmM3wi.ZAfQQdZmNvOBWnBka5whrmiWDXR8t9YS1QU.rRnnb6r9ACZF5RVcfMErplDg6nL2AsuGEqACqkzhC_CuAOcT4AyHPS3V.aSfb2dVo9ADJ8QheAQZs_a4KY5reEEZRXyZFBwRu_tsbZptgOr7MyePTaDfMgfWo"  # À MODIFIER

# User-Agent pour imiter un navigateur réel
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# =====================================================
# SYSTÈME DE CACHE INTELLIGENT
# =====================================================

class CloudflareSession:
    """Gère les sessions HTTP avec le cookie Cloudflare"""
    
    def __init__(self, cf_clearance: str, user_agent: str):
        self.session = requests.Session()
        
        # Configurer les headers comme un vrai navigateur
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        })
        
        # Ajouter le cookie cf_clearance
        self.session.cookies.set('cf_clearance', cf_clearance, domain='.noshydra.com')
        
        # Timestamp de création pour détecter l'expiration
        self.created_at = time.time()
        self.cookie_lifetime = 15 * 60  # 15 minutes en secondes
        
        print(f"🔐 Session Cloudflare initialisée avec le cookie")
    
    def is_cookie_expired(self) -> bool:
        """Vérifie si le cookie a probablement expiré"""
        elapsed = time.time() - self.created_at
        return elapsed > self.cookie_lifetime
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """Effectue une requête GET avec le cookie Cloudflare"""
        if self.is_cookie_expired():
            print("⚠️ ATTENTION: Le cookie cf_clearance a probablement expiré (>15 min)")
            print("   Récupérez un nouveau cookie depuis votre navigateur et relancez le script")
        
        return self.session.get(url, **kwargs)

class CacheManager:
    """Gère le cache des appels API pour éviter les requêtes répétées"""
    
    def __init__(self, cache_folder: Path):
        self.cache_folder = cache_folder
        self.cache_folder.mkdir(parents=True, exist_ok=True)
        print(f"💾 Système de cache initialisé: {cache_folder}")
    
    def get_cache_file(self, cache_type: str, key: str) -> Path:
        """Génère le chemin du fichier de cache pour une clé donnée"""
        # Créer un sous-dossier par type de cache
        type_folder = self.cache_folder / cache_type
        type_folder.mkdir(exist_ok=True)
        return type_folder / f"{key}.json"
    
    def get(self, cache_type: str, key: str) -> Optional[Dict]:
        """Récupère une valeur du cache"""
        cache_file = self.get_cache_file(cache_type, key)
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None
        return None
    
    def set(self, cache_type: str, key: str, value: Dict):
        """Sauvegarde une valeur dans le cache"""
        cache_file = self.get_cache_file(cache_type, key)
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(value, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Erreur lors de la sauvegarde du cache: {e}")
    
    def exists(self, cache_type: str, key: str) -> bool:
        """Vérifie si une clé existe dans le cache"""
        return self.get_cache_file(cache_type, key).exists()

# =====================================================
# GESTIONNAIRE DE DONNÉES DE JEU
# =====================================================

class GameDataManager:
    """Gestionnaire des données de jeu avec cache NosHydra"""
    
    def __init__(self, data_path: Path, cache_manager: CacheManager, cf_session: CloudflareSession):
        self.data_path = data_path
        self.maps_folder = MAPS_FOLDER
        self.cache = cache_manager
        self.cf_session = cf_session  # Session avec le cookie Cloudflare
        self.npcs_data = {}
        self.monsters_data = {}
        self.maps_info = {}
        
        print("📂 Chargement des fichiers de données...")
        self.load_all_data()
        print("✅ Données chargées avec succès\n")
    
    def load_all_data(self):
        """Charge tous les fichiers JSON de base"""
        try:
            # Charger les NPCs
            if NPCS_JSON.exists():
                with open(NPCS_JSON, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Créer un index par vnum (id) ET par nom
                    if isinstance(data, list):
                        self.npcs_data = {npc["id"]: npc for npc in data}
                    else:
                        self.npcs_data = data
                print(f"  ✓ NPCs: {len(self.npcs_data)} chargés")
            
            # Charger les monstres
            if MONSTERS_JSON.exists():
                with open(MONSTERS_JSON, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.monsters_data = {monster["id"]: monster for monster in data}
                    else:
                        self.monsters_data = data
                print(f"  ✓ Monstres: {len(self.monsters_data)} chargés")
            
            # Charger les infos de maps
            if MAPS_JSON.exists():
                with open(MAPS_JSON, 'r', encoding='utf-8') as f:
                    self.maps_info = json.load(f)
                print(f"  ✓ Infos maps: {len(self.maps_info)} chargées")
            
            # Vérifier le dossier maps
            if self.maps_folder.exists():
                map_files = list(self.maps_folder.glob("c_map_*.json"))
                print(f"  ✓ Fichiers de maps: {len(map_files)} disponibles")
            else:
                print(f"  ⚠️ Dossier maps/ non trouvé: {self.maps_folder}")
                self.maps_folder.mkdir(parents=True, exist_ok=True)
                
        except Exception as e:
            print(f"❌ Erreur lors du chargement des données: {e}")
            raise
    
    def find_npc_by_name(self, name_pattern: str) -> Optional[Dict]:
        """Trouve un NPC par son nom (français)"""
        name_lower = name_pattern.lower()
        for npc in self.npcs_data.values():
            npc_name = npc.get("name", {}).get("fr", "").lower()
            if name_lower in npc_name or npc_name in name_lower:
                return npc
        return None
    
    def find_monster_by_name(self, name_pattern: str) -> Optional[Dict]:
        """Trouve un monstre par son nom (français)"""
        name_lower = name_pattern.lower()
        for monster in self.monsters_data.values():
            monster_name = monster.get("name", {}).get("fr", "").lower()
            if name_lower in monster_name or monster_name in name_lower:
                return monster
        return None
    
    def get_map_name(self, map_id: int) -> str:
        """Récupère le nom français d'une map"""
        map_info = self.maps_info.get(str(map_id), {})
        return map_info.get("name", {}).get("fr", f"Map {map_id}")
    
    def load_map_file(self, map_id: int) -> Optional[Dict]:
        """Charge le fichier c_map_X.json d'une map"""
        map_file = self.maps_folder / f"c_map_{map_id}.json"
        if map_file.exists():
            try:
                with open(map_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Erreur lecture map {map_id}: {e}")
                return None
        return None
    
    def find_npc_on_map(self, map_id: int, npc_vnum: int) -> Optional[Tuple[int, int]]:
        """Trouve les coordonnées d'un NPC sur une map spécifique"""
        map_data = self.load_map_file(map_id)
        if not map_data:
            return None
        
        for npc in map_data.get("npcs", []):
            if npc["vnum"] == npc_vnum:
                return (npc["x"], npc["y"])
        return None
    
    def search_npc_location(self, npc_vnum: int) -> Optional[int]:
        """
        Cherche dans tous les fichiers c_map_X.json pour trouver
        sur quelle map se trouve un NPC donné
        """
        # Vérifier d'abord le cache
        cache_key = f"npc_location_{npc_vnum}"
        cached = self.cache.get("npc_locations", cache_key)
        if cached:
            print(f"  💾 NPC vnum {npc_vnum} trouvé dans le cache: map {cached['map_id']}")
            return cached["map_id"]
        
        print(f"  🔍 Recherche du NPC vnum {npc_vnum} dans toutes les maps...")
        
        # Parcourir tous les fichiers c_map_X.json
        for map_id in range(1, 413):  # De 1 à 412
            map_data = self.load_map_file(map_id)
            if not map_data:
                continue
            
            # Chercher le NPC dans cette map
            for npc in map_data.get("npcs", []):
                if npc["vnum"] == npc_vnum:
                    print(f"  ✓ NPC trouvé sur la map {map_id} ({self.get_map_name(map_id)})")
                    
                    # Sauvegarder dans le cache
                    self.cache.set("npc_locations", cache_key, {
                        "map_id": map_id,
                        "npc_vnum": npc_vnum,
                        "x": npc["x"],
                        "y": npc["y"]
                    })
                    
                    return map_id
        
        print(f"  ⚠️ NPC vnum {npc_vnum} non trouvé sur aucune map")
        return None
    
    def get_pathfinding(self, from_map: int, to_map: int) -> List[int]:
        """
        Obtient le chemin entre deux maps via NosHydra
        Utilise le cache pour éviter les appels répétés
        """
        # Vérifier le cache d'abord
        cache_key = f"{from_map}_to_{to_map}"
        cached = self.cache.get("pathfinding", cache_key)
        if cached:
            print(f"  💾 Chemin {from_map}→{to_map} trouvé dans le cache")
            return cached.get("path", [])
        
        # Appel à NosHydra avec le cookie Cloudflare
        print(f"  🌐 Appel NosHydra pour pathfinding {from_map}→{to_map}")
        try:
            url = f"{NOSHYDRA_BASE_URL}/map-explorer/find/{from_map}/{to_map}"
            response = self.cf_session.get(url, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            path = result.get("path", [])
            
            # Sauvegarder dans le cache
            self.cache.set("pathfinding", cache_key, {
                "from": from_map,
                "to": to_map,
                "path": path
            })
            
            print(f"  ✓ Chemin obtenu et mis en cache")
            return path
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                print(f"  ❌ Erreur 403: Cookie Cloudflare invalide ou expiré")
                print(f"      Récupérez un nouveau cookie depuis votre navigateur")
            else:
                print(f"  ❌ Erreur HTTP {e.response.status_code}")
            return []
        except Exception as e:
            print(f"  ❌ Erreur NosHydra pathfinding: {e}")
            return []
    
    def get_portal_to_next_map(self, current_map: int, next_map: int) -> Optional[Tuple[int, int]]:
        """
        Trouve les coordonnées du portail qui mène de current_map vers next_map
        """
        map_data = self.load_map_file(current_map)
        if not map_data:
            return None
        
        for portal in map_data.get("portals", []):
            if portal["destination_map_id"] == next_map:
                return (portal["source_map_x"], portal["source_map_y"])
        
        return None

# =====================================================
# CLASSE PRINCIPALE DU BOT
# =====================================================

class NostaleQuestBot:
    """Bot pour automatiser la quête Act 2-1 de Nostale"""
    
    def __init__(self, character_name: str, data_manager: GameDataManager):
        print(f"🔌 Connexion au bot Phoenix pour '{character_name}'...")
        self.client: PhoenixApi = create_api_from_name(character_name)
        self.data = data_manager
        self.current_map_id = None
        self.current_x = 0
        self.current_y = 0
        self.update_position()
        print(f"✅ Connecté ! Position: {self.data.get_map_name(self.current_map_id)} "
              f"({self.current_x}, {self.current_y})\n")
    
    def update_position(self):
        """Met à jour la position actuelle du personnage"""
        try:
            player_data = self.client.player_obj_manager.get_player_obj_manager()
            self.current_map_id = player_data["player"]["current_map_id"]
            self.current_x = player_data["position"]["x"]
            self.current_y = player_data["position"]["y"]
        except Exception as e:
            print(f"⚠️ Erreur mise à jour position: {e}")
    
    # =====================================================
    # NAVIGATION INTELLIGENTE
    # =====================================================
    
    def travel_to_map(self, target_map: int) -> bool:
        """Voyage vers une map cible en utilisant le pathfinding avec cache"""
        self.update_position()
        
        if self.current_map_id == target_map:
            print(f"  ℹ️ Déjà sur {self.data.get_map_name(target_map)}")
            return True
        
        # Obtenir le chemin (depuis le cache ou NosHydra)
        path = self.data.get_pathfinding(self.current_map_id, target_map)
        if not path or len(path) < 2:
            print(f"❌ Aucun chemin trouvé vers {self.data.get_map_name(target_map)}")
            return False
        
        # Afficher le trajet
        map_names = [self.data.get_map_name(m) for m in path]
        print(f"🗺️ Trajet: {' → '.join(map_names)}")
        
        # Parcourir le chemin
        for i in range(len(path) - 1):
            current = path[i]
            next_map = path[i + 1]
            
            # Vérifier la synchronisation
            self.update_position()
            if self.current_map_id != current:
                print(f"⚠️ Désynchronisation: attendu map {current}, "
                      f"actuellement sur map {self.current_map_id}")
                # Tenter de recalculer le chemin depuis la position actuelle
                return self.travel_to_map(target_map)
            
            # Trouver le portail
            portal_pos = self.data.get_portal_to_next_map(current, next_map)
            if not portal_pos:
                print(f"❌ Portail non trouvé: {self.data.get_map_name(current)} "
                      f"→ {self.data.get_map_name(next_map)}")
                return False
            
            print(f"  🚪 Portail vers {self.data.get_map_name(next_map)} en "
                  f"({portal_pos[0]}, {portal_pos[1]})")
            
            # Se déplacer vers le portail et attendre le changement de map
            self.walk_to(portal_pos[0], portal_pos[1], wait=2.0)
            time.sleep(1.5)
        
        self.update_position()
        if self.current_map_id == target_map:
            print(f"✅ Arrivé à {self.data.get_map_name(target_map)}")
            return True
        else:
            print(f"⚠️ Échec: sur map {self.current_map_id} au lieu de {target_map}")
            return False
    
    def walk_to(self, x: int, y: int, wait: float = 1.0):
        """Déplace le personnage vers des coordonnées"""
        print(f"    🚶 → ({x}, {y})")
        try:
            self.client.player_obj_manager.walk(x=x, y=y)
            time.sleep(wait)
            self.update_position()
        except Exception as e:
            print(f"    ⚠️ Erreur déplacement: {e}")
    
    # =====================================================
    # INTERACTION AVEC LE JEU
    # =====================================================
    
    def go_to_npc_and_talk(self, npc_name: str) -> bool:
        """
        Trouve un NPC par son nom, voyage jusqu'à lui et lui parle
        C'est la méthode principale qui orchestre tout le processus
        """
        print(f"\n💬 Recherche de {npc_name}")
        print("-" * 60)
        
        # Étape 1: Trouver le NPC dans la base de données
        npc_info = self.data.find_npc_by_name(npc_name)
        if not npc_info:
            print(f"❌ NPC '{npc_name}' non trouvé dans npcs.json")
            return False
        
        npc_vnum = npc_info["id"]
        npc_display_name = npc_info.get("name", {}).get("fr", npc_name)
        print(f"  ✓ NPC trouvé: {npc_display_name} (vnum: {npc_vnum})")
        
        # Étape 2: Chercher sur quelle map se trouve ce NPC
        npc_map = self.data.search_npc_location(npc_vnum)
        if not npc_map:
            print(f"❌ Impossible de localiser {npc_display_name}")
            return False
        
        # Étape 3: Voyager jusqu'à cette map
        print(f"  🗺️ Destination: {self.data.get_map_name(npc_map)}")
        if not self.travel_to_map(npc_map):
            return False
        
        # Étape 4: Trouver les coordonnées exactes du NPC sur cette map
        npc_pos = self.data.find_npc_on_map(npc_map, npc_vnum)
        if not npc_pos:
            print(f"⚠️ Coordonnées de {npc_display_name} introuvables")
            return False
        
        print(f"  📍 Position: ({npc_pos[0]}, {npc_pos[1]})")
        
        # Étape 5: Se déplacer vers le NPC
        self.walk_to(npc_pos[0], npc_pos[1], wait=1.5)
        
        # Étape 6: Trouver l'ID d'entité du NPC et lui parler
        try:
            npcs = self.client.scene_manager.get_npcs()
            npc_entity_id = None
            
            for npc in npcs.get("npcs", []):
                if npc.get("vnum") == npc_vnum:
                    npc_entity_id = npc["id"]
                    break
            
            if npc_entity_id:
                print(f"  💬 Conversation avec {npc_display_name}")
                self.client.packet_manager.send(f"npc_req 2 {npc_entity_id}")
                time.sleep(1.5)
                return True
            else:
                print(f"  ⚠️ {npc_display_name} non visible sur la map")
                return False
                
        except Exception as e:
            print(f"  ❌ Erreur lors de la conversation: {e}")
            return False
    
    def attack_monster_by_name(self, monster_name: str, count: int):
        """Attaque des monstres en cherchant leur nom"""
        monster_info = self.data.find_monster_by_name(monster_name)
        if not monster_info:
            print(f"⚠️ Monstre '{monster_name}' non trouvé")
            return
        
        monster_vnum = monster_info["id"]
        monster_display_name = monster_info.get("name", {}).get("fr", monster_name)
        
        print(f"  ⚔️ Chasse de {count}x {monster_display_name} (vnum: {monster_vnum})")
        
        killed = 0
        timeout = time.time() + 300  # 5 minutes max
        
        while killed < count and time.time() < timeout:
            try:
                monsters = self.client.scene_manager.get_monsters()
                
                target = None
                for monster in monsters.get("monsters", []):
                    if monster.get("vnum") == monster_vnum:
                        target = monster
                        break
                
                if target:
                    # Se rapprocher si nécessaire
                    monster_pos = target["position"]
                    distance = abs(self.current_x - monster_pos["x"]) + \
                              abs(self.current_y - monster_pos["y"])
                    
                    if distance > 2:
                        self.walk_to(monster_pos["x"], monster_pos["y"], wait=0.5)
                    
                    # Attaquer
                    self.client.player_obj_manager.attack(
                        entity_type=2,
                        entity_id=target["id"],
                        skill_id=0
                    )
                    
                    time.sleep(3)
                    killed += 1
                    print(f"    ✓ {killed}/{count}")
                else:
                    print(f"    ⏳ Recherche de {monster_display_name}...")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"    ⚠️ Erreur combat: {e}")
                time.sleep(2)
        
        if killed >= count:
            print(f"  ✅ {count}x {monster_display_name} éliminés")
        else:
            print(f"  ⚠️ Timeout: {killed}/{count}")
    
    # =====================================================
    # QUÊTE ACT 2-1
    # =====================================================
    
    def do_act_2_1(self):
        """Exécute la quête Act 2-1 complète"""
        print("\n" + "=" * 70)
        print("🎯 QUÊTE ACT 2-1: ÉRIGE UN AVANT-POSTE DE NOSCAMP")
        print("=" * 70 + "\n")
        
        try:
            # ÉTAPE 1: Chef Koaren
            print("\n📋 ÉTAPE 1: Conversation avec Chef Koaren")
            print("=" * 70)
            self.go_to_npc_and_talk("Koaren")
            time.sleep(2)
            
            # ÉTAPE 2: Colly sur la map 20
            print("\n📋 ÉTAPE 2: Conversation avec Colly")
            print("=" * 70)
            self.go_to_npc_and_talk("Colly")
            time.sleep(2)
            
            # ÉTAPE 3: Slugg
            print("\n📋 ÉTAPE 3: Conversation avec Slugg")
            print("=" * 70)
            self.go_to_npc_and_talk("Slugg")
            time.sleep(2)
            
            # ÉTAPE 4: Annie
            print("\n📋 ÉTAPE 4: Conversation avec Annie")
            print("=" * 70)
            self.go_to_npc_and_talk("Annie")
            time.sleep(2)
            
            # ÉTAPE 5: Mimi Mentor
            print("\n📋 ÉTAPE 5: Conversation avec Mimi Mentor")
            print("=" * 70)
            self.go_to_npc_and_talk("Mimi Mentor")
            time.sleep(2)
            
            print("\n" + "=" * 70)
            print("✅ QUÊTE ACT 2-1 - ÉTAPES PRINCIPALES COMPLÉTÉES")
            print("=" * 70 + "\n")
            
        except KeyboardInterrupt:
            print("\n⚠️ Quête interrompue par l'utilisateur")
        except Exception as e:
            print(f"\n❌ Erreur durant la quête: {e}")
            import traceback
            traceback.print_exc()

# =====================================================
# POINT D'ENTRÉE
# =====================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║        BOT PHOENIX - QUÊTE ACT 2-1 NOSTALE                       ║
║        Avec système de cache intelligent NosHydra                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    print("⚠️ STRUCTURE REQUISE:")
    print("  ./data/")
    print("    ├── npcs.json")
    print("    ├── monsters.json")
    print("    ├── maps.json")
    print("    ├── maps/")
    print("    │   ├── c_map_1.json")
    print("    │   ├── c_map_2.json")
    print("    │   └── ... (c_map_1 à c_map_412)")
    print("    └── cache/ (créé automatiquement)\n")
    
    print("🔐 COOKIE CLOUDFLARE:")
    print("  1. Allez sur https://www.noshydra.com dans votre navigateur")
    print("  2. Appuyez sur F12 > Application (Chrome) ou Storage (Firefox)")
    print("  3. Cookies > https://www.noshydra.com > cf_clearance")
    print("  4. Copiez la valeur et collez-la dans CF_CLEARANCE_COOKIE\n")
    
    # Vérifications
    if not DATA_PATH.exists():
        print(f"❌ Dossier {DATA_PATH} non trouvé")
        exit(1)
    
    if not MAPS_FOLDER.exists():
        print(f"❌ Dossier {MAPS_FOLDER} non trouvé")
        exit(1)
    
    if CF_CLEARANCE_COOKIE == "VOTRE_COOKIE_ICI":
        print("❌ Cookie Cloudflare non configuré")
        print("   Modifiez CF_CLEARANCE_COOKIE dans le script\n")
        exit(1)
    
    input("Appuyez sur Entrée pour démarrer...\n")
    
    try:
        # Initialiser la session Cloudflare
        cf_session = CloudflareSession(CF_CLEARANCE_COOKIE, USER_AGENT)
        
        # Initialiser le cache
        cache_manager = CacheManager(CACHE_FOLDER)
        
        # Charger les données
        data_manager = GameDataManager(DATA_PATH, cache_manager, cf_session)
        
        # Créer le bot
        bot = NostaleQuestBot(CHARACTER_NAME, data_manager)
        
        # Lancer la quête
        bot.do_act_2_1()
        
    except KeyboardInterrupt:
        print("\n⚠️ Arrêt du bot par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()