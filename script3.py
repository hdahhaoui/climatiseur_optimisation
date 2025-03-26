import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote
import re
import json

# Clé API et modèle DeepSeek
DEEPSEEK_API_KEY = "sk-c2463319fd4d461d9172e8b5b49936dd"
DEEPSEEK_MODEL = "deepseek-chat-1.3"

# Option pour activer le fallback de scraping local (désactivé par défaut, recommandé sur le Cloud)
SCRAPING_ENABLED = True  # À désactiver sur Streamlit Cloud

# Fonction pour analyser/convertir une valeur de puissance fournie sous forme de texte (avec unité)
def parse_power_value(val_str: str):
    """Convertit une chaîne contenant une puissance (W, kW, BTU/h) en valeur numérique (W)."""
    s = val_str.strip()
    s_lower = s.lower()
    # Retirer d'éventuelles mentions "/h" (ex: "BTU/h") pour simplifier
    s_lower = s_lower.replace('/h', '').replace('hour', '')
    match = re.search(r'(\d+[\d\.\,]*)\s*(kw|w|btu)', s_lower)
    if not match:
        return None
    num_str, unit = match.groups()
    try:
        value = float(num_str.replace(',', '.'))
    except:
        return None
    unit = unit.lower()
    if unit == 'w':
        return value
    if unit == 'kw':
        return value * 1000
    if unit == 'btu':
        # 1 BTU/h ≈ 0.29307 W
        return value * 0.29307107
    return value

# Fonction pour extraire la classe énergétique depuis un texte (A, A+, A++, ..., G)
def find_energy_class(text: str):
    """Recherche la classe énergétique (A...G avec +) dans le texte."""
    # Recherche d'une mention explicite "classe énergétique" ou "energy class"
    lines = text.splitlines()
    for segment in lines:
        seg_lower = segment.lower()
        if "classe énergétique" in seg_lower or "classe energetique" in seg_lower or "energy class" in seg_lower:
            # Isoler la partie après ":" (s'il y en a) pour trouver la valeur de classe
            part = segment
            if ':' in segment:
                part = segment.split(':', 1)[1]
            match = re.search(r'\b([A-G]\+{0,3})\b', part.strip())
            if match:
                return match.group(1)
    # Si pas de libellé explicite, on cherche toute mention de A+/A++...
    match = re.search(r'\b([A-G]\+{1,3})\b', text)
    if match:
        return match.group(1)
    return None

# Fonction principale pour parser la réponse de l'API DeepSeek ou du texte extrait d'une page web
def parse_ac_specs(text_response: str):
    """
    Extrait les données de consommation, puissance frigorifique, technologie inverter et classe énergétique
    à partir d'une réponse textuelle (JSON ou texte structuré).
    """
    data = {"consumption_w": None, "cooling_w": None, "inverter": None, "energy_class": None}
    if not text_response:
        return data
    text = text_response.strip()

    # 1. Tentative de parser en JSON structuré si la réponse semble être du JSON
    if text.startswith('{') or text.startswith('['):
        try:
            resp_json = json.loads(text)
        except json.JSONDecodeError:
            resp_json = None
        if resp_json:
            # Parcourir les éléments JSON pour trouver nos champs d'intérêt
            # (les clés peuvent être en français ou anglais selon la réponse)
            for key, val in resp_json.items() if isinstance(resp_json, dict) else []:
                key_low = key.lower()
                if "consommation" in key_low or "consumption" in key_low or "puissance absorb" in key_low or "power" in key_low:
                    # Consommation électrique
                    if isinstance(val, (int, float)):
                        data["consumption_w"] = float(val)
                    elif isinstance(val, str):
                        conv = parse_power_value(val)
                        if conv is not None:
                            data["consumption_w"] = conv
                if "frigorifique" in key_low or "cooling" in key_low or "capacity" in key_low or "cold" in key_low:
                    # Puissance frigorifique
                    if isinstance(val, (int, float)):
                        data["cooling_w"] = float(val)
                    elif isinstance(val, str):
                        conv = parse_power_value(val)
                        if conv is not None:
                            data["cooling_w"] = conv
                if "inverter" in key_low or "technologie" in key_low or "technology" in key_low:
                    # Technologie (Inverter ou non)
                    if isinstance(val, bool):
                        data["inverter"] = "Inverter" if val else "Non-Inverter"
                    elif isinstance(val, str):
                        inv_val = val.lower()
                        if "non" in inv_val or "pas" in inv_val or inv_val in ["false", "no", "0"]:
                            data["inverter"] = "Non-Inverter"
                        elif "inverter" in inv_val or inv_val in ["true", "oui", "yes", "1"]:
                            data["inverter"] = "Inverter"
                        else:
                            data["inverter"] = val  # valeur textuelle telle quelle si autre
                if "classe" in key_low or "class" in key_low or "rating" in key_low:
                    # Classe énergétique
                    if isinstance(val, str):
                        data["energy_class"] = val.strip()
                    else:
                        data["energy_class"] = str(val)
            # Si on a obtenu consommation et puissance, on peut retourner directement
            if data["consumption_w"] is not None and data["cooling_w"] is not None:
                # Nettoyage finale des valeurs (au cas où en string)
                if isinstance(data["consumption_w"], str):
                    data["consumption_w"] = parse_power_value(data["consumption_w"])
                if isinstance(data["cooling_w"], str):
                    data["cooling_w"] = parse_power_value(data["cooling_w"])
                return data
    # 2. Si la réponse n'est pas JSON ou incomplète, on parse en texte libre structuré
    lower = text.lower()
    # Rechercher toutes les occurrences de nombres suivis d'unités W, kW ou BTU
    matches = re.findall(r'(\d+[\d\.\,]*)(?:\s*)(kw|w|btu)', lower)
    cons_val = None
    cool_val = None
    for num_str, unit in matches:
        try:
            value = float(num_str.replace(',', '.'))
        except:
            continue
        unit = unit.lower()
        if unit == 'w':
            watts = value
        elif unit == 'kw':
            watts = value * 1000
        elif unit == 'btu':
            watts = value * 0.29307107  # conversion BTU->W
        else:
            watts = value
        # Chercher des mots-clés autour du nombre pour déterminer s'il s'agit de la consommation ou de la puissance frigorifique
        idx = lower.find(num_str + unit)
        context = lower[max(0, idx-20): idx+20] if idx != -1 else ""
        if any(word in context for word in ["consommation", "consomm\u00e9e", "absorbé", "absorbee", "electri", "input"]):
            cons_val = watts
        if any(word in context for word in ["frigorifique", "calorifique", "froid", "rafraich", "cooling", "capacity"]):
            cool_val = watts
    # S'il n'y a pas eu de contexte clair, tenter d'attribuer par différence de magnitude (généralement, puissance frigorifique >> consommation)
    if (cons_val is None or cool_val is None) and len(matches) == 2:
        vals = []
        for num_str, unit in matches:
            try:
                v = float(num_str.replace(',', '.'))
            except:
                continue
            if unit.lower() == 'w':
                v_w = v
            elif unit.lower() == 'kw':
                v_w = v * 1000
            elif unit.lower() == 'btu':
                v_w = v * 0.29307107
            else:
                v_w = v
            vals.append(v_w)
        if len(vals) == 2:
            # Plus grand = puissance frigorifique, plus petit = consommation (supposé)
            if vals[0] > vals[1]:
                cool_val = vals[0]
                cons_val = vals[1]
            else:
                cool_val = vals[1]
                cons_val = vals[0]
    data["consumption_w"] = cons_val
    data["cooling_w"] = cool_val
    # Technologie inverter (oui/non)
    if "inverter" in lower:
        # Si on trouve explicitement "non inverter" ou "pas inverter"
        if "non inverter" in lower or "pas inverter" in lower:
            data["inverter"] = "Non-Inverter"
        else:
            data["inverter"] = "Inverter"
    # Classe énergétique (A, A+, A++, ...)
    data["energy_class"] = find_energy_class(text) or data["energy_class"]
    return data

# Fonction d'interrogation de l'API DeepSeek
def fetch_specs_from_deepseek(model: str):
    """Interroge l’API DeepSeek pour le modèle donné et renvoie le texte de réponse."""
    api_url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    # Préparation du prompt pour ne demander que les données essentielles
    user_prompt = (
        f"Fiche technique simplifiée pour le climatiseur \"{model}\" : "
        "donne uniquement la consommation électrique (en W), la puissance frigorifique (en W), "
        "la technologie (inverter ou non) et la classe énergétique si disponible."
    )
    # Messages du chat : on peut ajouter un rôle système pour cadrer la réponse
    messages = [
        {"role": "system", "content": "Vous êtes un assistant technique qui fournit des données chiffrées précises."},
        {"role": "user", "content": user_prompt}
    ]
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 300
    }
    try:
        res = requests.post(api_url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            # L'API DeepSeek est compatible avec le format OpenAI
            response_json = res.json()
            # Extraire le contenu de la réponse de l'assistant
            answer = response_json["choices"][0]["message"]["content"]
            return answer
        else:
            # En cas de code de statut non OK, on lève une exception pour gérer le fallback
            raise Exception(f"HTTP {res.status_code}: {res.text}")
    except Exception as e:
        # On retourne None si échec (géré par le fallback ensuite)
        print(f"Erreur API DeepSeek: {e}")
        return None

# Fonction de fallback : scraping web pour obtenir les spécifications
def fetch_specs_via_scraping(model: str):
    """Recherche les spécifications du modèle via scraping (recherche Google simulée) et renvoie les données extraites."""
    query = f"{model} climatiseur fiche technique"
    # URL de recherche Google (note: peut être bloqué sur certaines plateformes)
    search_url = "https://www.google.com/search?q=" + requests.utils.requote_uri(query)
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(search_url, headers=headers, timeout=5)
    except Exception as e:
        return None
    if res.status_code != 200:
        return None
    soup = BeautifulSoup(res.text, 'html.parser')
    result_link = None
    # Extraire le premier lien de résultat (en évitant les liens internes Google)
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('/url?'):
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            url = qs.get('q', [None])[0]
            if url:
                url = unquote(url)
                # Ignorer les liens Google ou YouTube, ainsi que les PDF (non parsables ici)
                if "google." in url or "youtube.com" in url or url.lower().endswith(('.pdf', '.PDF')):
                    continue
                result_link = url
                break
    if not result_link:
        return None
    # Télécharger la page du premier résultat
    try:
        page_res = requests.get(result_link, headers=headers, timeout=5)
    except Exception as e:
        return None
    if page_res.status_code != 200:
        return None
    page_html = page_res.text
    soup_page = BeautifulSoup(page_html, 'html.parser')
    # Supprimer les scripts et styles pour ne garder que le texte utile
    for script in soup_page(["script", "style"]):
        script.decompose()
    text = soup_page.get_text(separator=" ")
    data = parse_ac_specs(text)
    # Vérifier si on a bien obtenu les valeurs essentielles, sinon tenter un deuxième lien de résultat
    if (data.get("consumption_w") is None or data.get("cooling_w") is None):
        # Essayer le lien suivant dans la page de résultats
        second_link = None
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('/url?'):
                parsed = urlparse(href)
                qs = parse_qs(parsed.query)
                url = qs.get('q', [None])[0]
                if not url:
                    continue
                url = unquote(url)
                if "google." in url or "youtube.com" in url or url.lower().endswith(('.pdf', '.PDF')):
                    continue
                # passer le premier lien qu'on a déjà utilisé
                if result_link and url == result_link:
                    continue
                second_link = url
                break
        if second_link:
            try:
                page_res2 = requests.get(second_link, headers=headers, timeout=5)
                if page_res2.status_code == 200:
                    soup_page2 = BeautifulSoup(page_res2.text, 'html.parser')
                    for script in soup_page2(["script", "style"]):
                        script.decompose()
                    text2 = soup_page2.get_text(separator=" ")
                    data2 = parse_ac_specs(text2)
                    # Compléter les données manquantes avec ce second résultat
                    for key in data2:
                        if data.get(key) is None and data2.get(key) is not None:
                            data[key] = data2[key]
            except Exception:
                pass
    return data

# Définition de l'interface Streamlit
st.title("🌀 Simulation de consommation d'un climatiseur")
st.write("Cet outil récupère automatiquement les caractéristiques techniques essentielles d’un climatiseur (via API et web) afin de simuler sa consommation énergétique sur une journée.")

# Champ de saisie pour le modèle de climatiseur
model_name = st.text_input("**Modèle du climatiseur** (référence exacte) :", placeholder="Exemple : Samsung AR12TXFCAWKN")
if SCRAPING_ENABLED:
    st.warning("🔎 Le **scraping web** est activé pour la récupération de données (à utiliser de préférence en local).")
else:
    st.info("ℹ️ Le scraping web est désactivé par défaut (recommandé sur Streamlit Cloud). Seule l'API DeepSeek sera utilisée.")

# Bouton de recherche
if st.button("🔍 Obtenir les caractéristiques et simuler la consommation"):
    if not model_name.strip():
        st.error("Veuillez saisir un nom ou modèle de climatiseur pour continuer.")
    else:
        # Appel en priorité à l'API DeepSeek
        st.write(f"**Recherche des données pour \"{model_name}\"...**")
        api_response = fetch_specs_from_deepseek(model_name.strip())
        data = None
        if api_response:
            # Parser la réponse de l'API
            data = parse_ac_specs(api_response)
        # Si l'API n'a pas répondu ou données incomplètes, tenter le fallback
        if data is None or data.get("consumption_w") is None or data.get("cooling_w") is None:
            st.warning("L'API DeepSeek n'a pas fourni toutes les informations nécessaires. Activation du mode secours (scraping web)...")
            if SCRAPING_ENABLED:
                data = fetch_specs_via_scraping(model_name.strip())
            else:
                data = None  # Scraping désactivé, on restera None
        # Vérifier si on a bien obtenu des données exploitables
        if data is None or data.get("consumption_w") is None or data.get("cooling_w") is None:
            st.error("❌ Impossible de trouver les caractéristiques complètes pour ce modèle. Veuillez vérifier le nom du modèle ou essayer un autre modèle.")
        else:
            # Arrondi des valeurs numériques pour affichage (Watts)
            cons_w = int(round(data["consumption_w"])) if data.get("consumption_w") is not None else None
            cool_w = int(round(data["cooling_w"])) if data.get("cooling_w") is not None else None
            inv_tech = data.get("inverter")
            energy_class = data.get("energy_class")

            # Affichage des caractéristiques récupérées
            st.subheader("Caractéristiques techniques essentielles")
            cols = st.columns([1,1,1,1])
            cols[0].metric("Consommation électrique", f"{cons_w} W" if cons_w is not None else "N/A")
            cols[1].metric("Puissance frigorifique", f"{cool_w} W" if cool_w is not None else "N/A")
            # Pour technologie inverter, afficher Oui/Non ou valeur textuelle
            if inv_tech:
                if inv_tech.lower().startswith("non"):
                    cols[2].metric("Technologie", "Non-Inverter")
                else:
                    cols[2].metric("Technologie", "Inverter")
            else:
                cols[2].metric("Technologie", "N/A")
            cols[3].metric("Classe énergétique", energy_class if energy_class else "N/A")

            # Choix du nombre d'heures de fonctionnement par jour pour la simulation
            st.subheader("Simulation de la consommation sur 24h")
            st.write("Réglez le profil d'utilisation quotidienne du climatiseur :")
            hours = st.slider("Heures de fonctionnement par jour", min_value=0, max_value=24, value=8)
            if cons_w is None:
                st.error("Donnée de consommation indisponible, impossible de calculer la consommation énergétique.")
            else:
                if hours <= 0:
                    st.info("Choisissez un nombre d'heures d'utilisation supérieur à 0 pour calculer la consommation.")
                else:
                    # Calcul de la consommation journalière
                    daily_wh = cons_w * hours  # en Wh
                    daily_kwh = daily_wh / 1000.0
                    st.write(f"**Consommation journalière estimée** (pour {hours}h de fonctionnement) : **{daily_kwh:.2f} kWh**")
                    # Détail horaire (simple répartition sur les premières 'hours' heures de la journée)
                    profile = [cons_w/1000.0 if i < hours else 0 for i in range(24)]
                    df_profile = pd.DataFrame({"Consommation horaire (kWh)": profile}, index=[f"{h}h" for h in range(24)])
                    st.bar_chart(df_profile, height=200)
                    st.caption("Profil de consommation sur 24h (les heures où le climatiseur est allumé sont supposées consommer la puissance nominale).")

# Fin du code
