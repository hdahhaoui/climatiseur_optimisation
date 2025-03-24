import streamlit as st
import requests
import pandas as pd
import datetime
import json
import re

# Configuration de la page
st.set_page_config(page_title="Simulateur de Climatisation", page_icon="❄️", layout="wide")

# Clés API (à remplacer par vos propres clés si nécessaire)
DEESEEK_API_KEY = "sk-c2463319fd4d461d9172e8b5b49936dd" 
MODEL = "deepseek-chat"
OWM_API_KEY = "420227af9037639d0d68ac9deafead1a"

# Fonctions utilitaires avec mise en cache
@st.cache_data(show_spinner=False)
def get_ac_specs(modele: str):
    """Interroge l'API DeepSeek pour obtenir les caractéristiques du climatiseur donné."""
    if not modele:
        return None
    # Préparation de la requête API DeepSeek (compatible OpenAI)
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEESEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    # Message à envoyer (en français) pour obtenir les informations en JSON
    system_msg = {"role": "system", "content": "Vous êtes un assistant expert en climatiseurs."}
    user_msg = {"role": "user", "content": 
               f"Fournis les caractéristiques techniques du climatiseur modèle {modele}. "
               "Donne la consommation électrique en watts, la puissance frigorifique en watts, "
               "la classe énergétique (par exemple A, A+, etc.), et indique si la technologie inverter est présente. "
               "Réponds uniquement au format JSON avec les clés suivantes : "
               "consommation_electrique_W, puissance_frigorifique_W, classe_energetique, technologie_inverter."}
    data = {
        "model": "deepseek-chat",
        "messages": [system_msg, user_msg],
        "max_tokens": 200,
        "temperature": 0.0
    }
    try:
        res = requests.post(url, headers=headers, json=data, timeout=10)
    except Exception:
        return None
    if not res.ok:
        return None
    # Lecture de la réponse JSON
    result = res.json()
    # Extraire le contenu du message assistant
    content = None
    if isinstance(result, dict):
        # Si format OpenAI: chercher dans 'choices'
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
        else:
            # Format inattendu: tenter d'utiliser tel quel
            content = str(result)
    else:
        content = str(result)
    if not content:
        return None
    # Tenter de parser le contenu JSON retourné
    try:
        specs = json.loads(content)
    except json.JSONDecodeError:
        return None
    # Extraire et normaliser les valeurs importantes
    consommation_W = None
    capacite_W = None
    classe_energetique = None
    inverter_flag = None
    for key, val in specs.items():
        k = key.lower()
        if "consommation" in k:
            consommation_W = val
        elif "puissance" in k:
            capacite_W = val
        elif "classe" in k or "class" in k:
            classe_energetique = val
        elif "inverter" in k:
            inverter_flag = val
    # Fonction interne pour convertir une valeur de puissance en nombre (W)
    def parse_power(val):
        if val is None:
            return None
        # Si déjà un nombre (int/float)
        if isinstance(val, (int, float)):
            return float(val)
        # Si chaîne de caractères, extraire la partie numérique
        if isinstance(val, str):
            txt = val.replace(",", ".")
            numbers = re.findall(r"[\d\.]+", txt)
            if not numbers:
                return None
            num = float(numbers[0])
            # Adapter selon l'unité mentionnée dans le texte
            if "kw" in txt.lower():
                # Si par exemple "3.5 kW"
                if num < 50:  # on suppose que c'est en kW si le nombre est petit
                    num *= 1000.0
            if "btu" in txt.lower():
                # Conversion BTU -> Watts
                num *= 0.293
            return num
        return None
    # Convertir la consommation et la capacité en valeurs numériques (Watts)
    cons_val = parse_power(consommation_W)
    cap_val = parse_power(capacite_W)
    # Si la capacité semble être en BTU (ex: valeur élevée sans unité) et que la consommation est donnée en W
    if cap_val and cons_val:
        if cap_val > 1000 and cons_val > 0 and cap_val / cons_val > 5:
            # On interprète cap_val comme BTU et on convertit en W
            cap_val *= 0.293
    # Estimation de la valeur manquante si nécessaire (suppose COP ~3)
    if cons_val is None and cap_val:
        cons_val = cap_val / 3.0
    if cap_val is None and cons_val:
        cap_val = cons_val * 3.0
    if cons_val is None or cap_val is None:
        return None
    # Retourner un dict des spécifications utiles
    return {
        "consommation_W": cons_val,
        "capacite_W": cap_val,
        "classe_energetique": classe_energetique,
        "inverter": inverter_flag
    }

@st.cache_data(show_spinner=False)
def get_weather(ville: str):
    """Interroge l'API OpenWeatherMap pour obtenir la météo horaire (24h) de la ville donnée."""
    if not ville:
        return None
    # Géocodage de la ville pour obtenir lat & lon
    geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={ville}&limit=1&appid={OWM_API_KEY}"
    try:
        res = requests.get(geo_url, timeout=5)
    except Exception:
        return None
    if not res.ok or res.json() == []:
        return None  # ville non trouvée
    geo = res.json()[0]
    lat, lon = geo.get("lat"), geo.get("lon")
    if lat is None or lon is None:
        return None
    # Appel API pour les prévisions horaires sur 24h
    forecast_url = (f"https://api.openweathermap.org/data/2.5/onecall?"
                    f"lat={lat}&lon={lon}&exclude=minutely,daily,alerts&units=metric&appid={OWM_API_KEY}")
    try:
        res2 = requests.get(forecast_url, timeout=5)
    except Exception:
        return None
    if not res2.ok:
        return None
    weather_data = res2.json()
    # Ne garder que les 24 premières heures de prévision
    if "hourly" in weather_data:
        weather_data["hourly"] = weather_data["hourly"][:24]
    return weather_data

# Titre et description de l'application
st.title("Simulateur de Consommation d'un Climatiseur")
st.markdown(
    "Entrez les caractéristiques de votre climatiseur, la localisation et vos habitudes d'utilisation, "
    "puis comparez la consommation énergétique et le coût journalier selon deux scénarios d'usage."
)

# Formulaire de saisie des paramètres
with st.form("param_form"):
    modele = st.text_input("Nom du climatiseur (modèle) :")
    ville = st.text_input("Ville :")
    surface = st.number_input("Surface de la pièce (m²) :", min_value=1.0, value=20.0)
    isolation = st.selectbox("Niveau d'isolation de la pièce :", ["Bonne", "Moyenne", "Faible"])
    fenetres = st.selectbox("Présence de fenêtres :", ["Oui", "Non"])
    personnes = st.number_input("Nombre de personnes dans la pièce :", min_value=0, value=0)
    confort = st.number_input("Température de confort souhaitée (°C) :", min_value=16, max_value=30, value=24)
    prix_elec = st.number_input("Prix de l'électricité (DZD/kWh) :", min_value=0.0, value=5.0)
    nb_plages = st.number_input("Nombre de plages horaires d'occupation par jour :", min_value=1, max_value=4, value=1)
    # Saisie des plages horaires d'occupation
    horaires = []
    for i in range(int(nb_plages)):
        col1, col2 = st.columns(2)
        with col1:
            debut = st.number_input(f"Heure début plage {i+1} (0-23) :", min_value=0, max_value=23, key=f"deb{i}")
        with col2:
            fin = st.number_input(f"Heure fin plage {i+1} (incluse, 0-23) :", min_value=0, max_value=23, key=f"fin{i}")
        horaires.append((int(debut), int(fin)))
    submit = st.form_submit_button("Lancer la simulation")

if submit:
    # Validation des entrées utilisateur
    if not modele:
        st.error("Veuillez saisir le modèle du climatiseur.")
        st.stop()
    if not ville:
        st.error("Veuillez saisir le nom de la ville.")
        st.stop()
    # Vérification des plages horaires (fin doit être >= début)
    for idx, (deb, fin) in enumerate(horaires, start=1):
        if fin < deb:
            st.error(f"Plage {idx} invalide : l'heure de fin doit être supérieure ou égale à l'heure de début (pas de chevauchement minuit).")
            st.stop()
    # Appels API pour récupérer les données techniques et météo
    with st.spinner("Chargement des données depuis les API..."):
        specs = get_ac_specs(modele)
        weather = get_weather(ville)
    # Vérification des réponses des API
    if specs is None:
        st.error("Impossible de récupérer les caractéristiques du climatiseur. Vérifiez le modèle et réessayez.")
        st.stop()
    if weather is None or "hourly" not in weather:
        st.error("Impossible de récupérer les données météo pour cette ville. Vérifiez le nom de la ville.")
        st.stop()
    # Affichage des caractéristiques du climatiseur
    st.subheader("Caractéristiques du climatiseur")
    inv_str = "Oui" if specs.get("inverter") in [True, "True", "true", "oui", "Oui"] else "Non"
    st.markdown(f"**Modèle :** {modele}")
    st.markdown(f"**Puissance frigorifique :** {specs['capacite_W']:.0f} W")
    st.markdown(f"**Consommation électrique :** {specs['consommation_W']:.0f} W")
    if specs.get("classe_energetique"):
        st.markdown(f"**Classe énergétique :** {specs['classe_energetique']}")
    st.markdown(f"**Technologie inverter :** {inv_str}")
    # Préparation des données météo
    heure_values = list(range(len(weather["hourly"])))
    temperatures = [h.get("temp") for h in weather["hourly"]]
    # Construction du profil d'occupation sur 24h (tableau booléen)
    occupation = [False] * len(temperatures)
    for deb, fin in horaires:
        if deb <= fin:
            for h in range(deb, fin + 1):
                if 0 <= h < len(occupation):
                    occupation[h] = True
    # Calcul de la consommation horaire pour chaque scénario
    cons_scen1 = []  # consommation horaire (kWh) scénario 1
    cons_scen2 = []  # consommation horaire (kWh) scénario 2
    # Coefficient d'isolation (plus élevé = moins bien isolé -> plus de gain de chaleur)
    if isolation == "Bonne":
        coeff_iso = 1.0
    elif isolation == "Moyenne":
        coeff_iso = 2.0
    else:
        coeff_iso = 3.0
    # Impact des fenêtres sur les gains de chaleur
    if fenetres == "Oui":
        coeff_iso += 1.0
    # Paramètres du climatiseur
    cap = specs["capacite_W"]  # capacité de refroidissement en W
    cons_w = specs["consommation_W"]  # consommation électrique en W à pleine puissance
    # Boucle horaire
    for h, temp_ext in enumerate(temperatures):
        if occupation[h]:
            if temp_ext <= confort:
                # Pas de besoin de clim (temp extérieure inférieure ou égale à la consigne)
                duty1 = 0.0
            else:
                # Scénario 1 : climatisation classique
                delta = temp_ext - confort
                # Charge thermique (approx) : proportionnelle à la surface, à l'écart de température et au coeff d'isolation
                charge = coeff_iso * surface * delta + personnes * 100
                # Durée de fonctionnement de la clim sur l'heure (0 à 1) en fonction de la charge
                duty1 = charge / cap
                if duty1 > 1:
                    duty1 = 1.0  # la clim tourne à 100% de sa puissance (maximale)
            # Scénario 2 : usage optimisé
            if temp_ext <= confort + 2:
                # On attend que l'écart dépasse 2°C pour démarrer la clim
                duty2 = 0.0
            else:
                delta2 = temp_ext - (confort + 2)
                charge2 = coeff_iso * surface * delta2 + personnes * 100
                duty2 = charge2 / cap
                if duty2 > 1:
                    duty2 = 1.0
        else:
            # Pas d'occupation -> pas de clim utilisée
            duty1 = 0.0
            duty2 = 0.0
        # Consommation électrique en kWh durant cette heure
        cons_scen1.append(duty1 * cons_w / 1000.0)
        cons_scen2.append(duty2 * cons_w / 1000.0)
    # Calcul des consommations et coûts totaux
    total_cons_scen1 = sum(cons_scen1)
    total_cons_scen2 = sum(cons_scen2)
    total_cost_scen1 = total_cons_scen1 * prix_elec
    total_cost_scen2 = total_cons_scen2 * prix_elec
    # Affichage des résultats sous forme de tableau comparatif
    st.subheader("Comparatif de la consommation journalière")
    results_df = pd.DataFrame({
        "Scénario 1": [f"{total_cons_scen1:.2f} kWh", f"{total_cost_scen1:.2f} DZD"],
        "Scénario 2": [f"{total_cons_scen2:.2f} kWh", f"{total_cost_scen2:.2f} DZD"],
        "Économie": [f"{(total_cons_scen1 - total_cons_scen2):.2f} kWh", 
                     f"{(total_cost_scen1 - total_cost_scen2):.2f} DZD"]
    }, index=["Consommation", "Coût"])
    st.table(results_df)
    # Graphiques : température extérieure et consommations horaires
    st.subheader("Température extérieure sur 24h")
    df_temp = pd.DataFrame({"Température extérieure (°C)": temperatures})
    df_temp.index.name = "Heure"
    st.line_chart(df_temp)
    st.subheader("Consommation horaire de climatisation")
    df_cons = pd.DataFrame({
        "Scénario 1": cons_scen1,
        "Scénario 2": cons_scen2
    })
    df_cons.index.name = "Heure"
    st.line_chart(df_cons)
    # Recommandations personnalisées
    st.subheader("Recommandations pour optimiser votre climatisation")
    recommandations = []
    # Parcourir les périodes d'occupation pour identifier les moments d'allumage/extinction optimaux
    for deb, fin in horaires:
        # Calcul de l'heure de démarrage recommandée (scénario 2 vs scénario 1)
        h1 = None
        h2 = None
        for h in range(deb, fin + 1):
            if h < len(temperatures):
                if temperatures[h] > confort and h1 is None:
                    h1 = h
                if temperatures[h] > confort + 2 and h2 is None:
                    h2 = h
        if h1 is None:
            # Aucune clim nécessaire même en scénario 1
            continue
        if h2 is None:
            # Scénario 2 ne la démarre pas du tout pendant la plage
            recommandations.append(
                f"Sur la plage {deb}h-{fin}h, la climatisation peut rester **éteinte** : la température extérieure ne dépasse jamais {confort+2}°C."
            )
        elif h2 is not None and h1 is not None and h2 > h1:
            # Le scénario 2 démarre plus tard que le scénario 1
            recommandations.append(
                f"Attendez jusqu'à **{h2}h** avant d'allumer la clim (au lieu de {h1}h) car l'air extérieur est encore relativement frais en début de période."
            )
        # Calcul de l'heure d'extinction recommandée (scénario 2 vs scénario 1)
        l1 = None
        l2 = None
        for h in range(fin, deb - 1, -1):
            if h < len(temperatures):
                if temperatures[h] > confort and l1 is None:
                    l1 = h
                if temperatures[h] > confort + 2 and l2 is None:
                    l2 = h
        if l1 is None:
            continue
        if l2 is None:
            continue
        if l2 < l1 and l1 == fin:
            # Le scénario 2 éteint avant la fin de la plage
            recommandations.append(
                f"Éteignez la clim vers **{l2+1}h** plutôt que {l1+1}h, dès que la température extérieure redescend et devient plus supportable."
            )
    # Recommandation sur la consigne de température
    if confort < 30:
        recommandations.append(
            f"Ajustez la consigne si possible à **{min(confort+2, 30)}°C** au lieu de {confort}°C pour économiser de l'énergie."
        )
    # Recommandation sur l'aération naturelle ou ventilateur
    if fenetres == "Oui":
        recommandations.append(
            "Profitez de la **ventilation naturelle** en ouvrant les fenêtres lorsque l'air extérieur est plus frais que la consigne."
        )
    else:
        recommandations.append(
            "Utilisez un **ventilateur** pour vous rafraîchir lorsque la climatisation est coupée, surtout s'il n'y a pas de fenêtres."
        )
    # Affichage des recommandations
    for rec in recommandations:
        st.markdown("- " + rec)
    # Estimation des gains sur 7 jours
    economie_jour = total_cost_scen1 - total_cost_scen2
    economie_sem = 7 * economie_jour
    economie_kwh = 7 * (total_cons_scen1 - total_cons_scen2)
    st.markdown(
        f"**Gain estimé sur 7 jours :** environ **{economie_kwh:.1f} kWh** économisés, soit **{economie_sem:.0f} DZD** en moins sur la facture d'électricité."
    )
