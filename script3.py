import streamlit as st
import requests
import datetime
import math
import openai
import pandas as pd
import altair as alt

# Clés API (doivent être configurées dans les secrets de l'application Streamlit)
DEEPSEEK_API_KEY = st.secrets("DEEPSEEK_KEY", None)
OWM_API_KEY = st.secrets.get("OWMAPI_KEY", None)

# Tarif de l'électricité (DZD par kWh) - constant
TARIF_ELECTRICITE = 5  # 5 DZD/kWh

# Liste prédéfinie de villes algériennes avec leurs coordonnées (latitude, longitude)
VILLES = {
    "Adrar": (27.867, -0.283),
    "Alger": (36.753, 3.058),
    "Annaba": (36.90, 7.766),
    "Batna": (35.556, 6.174),
    "Béchar": (31.617, -2.217),
    "Béjaïa": (36.756, 5.084),
    "Biskra": (34.850, 5.730),
    "Constantine": (36.365, 6.615),
    "Ghardaïa": (32.490, 3.670),
    "Laghouat": (33.800, 2.865),
    "Oran": (35.699, -0.636),
    "Ouargla": (31.949, 5.325),
    "Sétif": (36.191, 5.414),
    "Tamanrasset": (22.785, 5.525),
    "Tizi Ouzou": (36.717, 4.050),
    "Tlemcen": (34.882, -1.314)
}

# Titre de l'application
st.title("Simulation de consommation énergétique d'un climatiseur (7 jours)")

# Section 1: Caractéristiques du climatiseur (IA DeepSeek ou saisie manuelle)
st.header("1. Données du climatiseur (via IA DeepSeek ou saisie manuelle)")

# Champ de texte pour entrer le modèle du climatiseur
modele = st.text_input("Modèle du climatiseur :", value="", 
                       help="Entrez la référence exacte du climatiseur (ex: Marque Modèle 1234)")

# Bouton pour interroger l'API DeepSeek avec le modèle saisi
deepseek_result = None
if st.button("Obtenir les données techniques via l'IA DeepSeek"):
    if DEEPSEEK_API_KEY:
        # Configuration de l'API DeepSeek (compatible OpenAI)
        import openai
        openai.api_base = "https://api.deepseek.com/v1"
        openai.api_key = DEEPSEEK_API_KEY
        # Préparation de la requête (on demande consommation, puissance frigorifique, type inverter)
        prompt = (f"Fournis les caractéristiques techniques du climatiseur {modele} : "
                  f"consommation électrique (en kW), puissance frigorifique (en kW) et préciser s'il s'agit d'un modèle inverter ou non.")
        try:
            response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            deepseek_text = response["choices"][0]["message"]["content"]
            # Extraction des données depuis la réponse texte de l'IA
            import re
            conso_val = None
            froid_val = None
            inverter_val = None
            # Rechercher un nombre pour la consommation électrique (kW)
            match_conso = re.search(r'consommation.*?([\d\.]+)\s*kW', deepseek_text, re.IGNORECASE)
            if match_conso:
                conso_val = float(match_conso.group(1))
            # Rechercher puissance frigorifique en kW ou en BTU (convertir BTU -> kW si trouvé)
            match_froid = re.search(r'puissance frigorifique.*?([\d\.]+)\s*kW', deepseek_text, re.IGNORECASE)
            if match_froid:
                froid_val = float(match_froid.group(1))
            else:
                match_froid_btu = re.search(r'puissance frigorifique.*?([\d,]+)\s*BTU', deepseek_text, re.IGNORECASE)
                if match_froid_btu:
                    try:
                        btu_val = float(match_froid_btu.group(1).replace(',', ''))
                        # Conversion BTU/h vers kW (1 BTU/h ≈ 0.00029307107 kW)
                        froid_val = round(btu_val * 0.00029307107, 2)
                    except:
                        froid_val = None
            # Rechercher mention de "inverter" ou "non-inverter"
            if re.search(r'inverter', deepseek_text, re.IGNORECASE):
                if re.search(r'non inverter', deepseek_text, re.IGNORECASE) or re.search(r"pas inverter", deepseek_text, re.IGNORECASE):
                    inverter_val = False
                else:
                    inverter_val = True
            # Stocker les résultats dans l'état de session pour réutilisation
            st.session_state["ac_modele"] = modele
            st.session_state["ac_conso"] = conso_val
            st.session_state["ac_froid"] = froid_val
            st.session_state["ac_inverter"] = inverter_val
            # Vérifier si on a bien obtenu toutes les infos
            if conso_val and froid_val and inverter_val is not None:
                st.session_state["ac_data_ok"] = True
            else:
                st.session_state["ac_data_ok"] = False
        except Exception as e:
            st.error("Échec de la récupération via l'API DeepSeek.")
            st.session_state["ac_data_ok"] = False
    else:
        st.warning("Clé API DeepSeek non configurée. Veuillez entrer les données manuellement.")
        st.session_state["ac_data_ok"] = False

# Formulaire de secours pour entrer manuellement les données du climatiseur si DeepSeek a échoué ou n'a pas fourni toutes les infos
if not st.session_state.get("ac_data_ok", False):
    st.write("**Veuillez renseigner manuellement les caractéristiques du climatiseur :**")
    # Valeurs par défaut (éventuellement pré-remplies par ce qui a pu être partiellement extrait via l'IA)
    conso_def = st.session_state.get("ac_conso", 1.0) or 1.0  # kW (1.0 par défaut)
    froid_def = st.session_state.get("ac_froid", 2.0) or 2.0  # kW (2.0 par défaut)
    inverter_def = st.session_state.get("ac_inverter", True)
    # Champs de saisie manuelle
    consommation_kw = st.number_input("Consommation électrique du climatiseur (kW) :", min_value=0.1, max_value=10.0, value=conso_def, step=0.1)
    puissance_frigo_kw = st.number_input("Puissance frigorifique (kW) :", min_value=0.1, max_value=20.0, value=froid_def, step=0.1)
    type_inverter = st.selectbox("Technologie :", options=["Inverter", "Non-inverter"], index=(0 if inverter_def else 1))
    est_inverter = (type_inverter == "Inverter")
    # On stocke ces valeurs saisies manuellement également
    st.session_state["ac_modele"] = modele or "Modèle inconnu"
    st.session_state["ac_conso"] = consommation_kw
    st.session_state["ac_froid"] = puissance_frigo_kw
    st.session_state["ac_inverter"] = est_inverter
    st.session_state["ac_data_ok"] = True
else:
    # Si DeepSeek a réussi à obtenir les données, on les récupère de l'état
    consommation_kw = st.session_state.get("ac_conso", 1.0) or 1.0
    puissance_frigo_kw = st.session_state.get("ac_froid", 2.0) or 2.0
    est_inverter = st.session_state.get("ac_inverter", True)

# Champs supplémentaires liés au climatiseur
# Âge du climatiseur (années) et fréquence d'entretien
age = st.number_input("Âge du climatiseur (en années) :", min_value=0, max_value=50, value=5, step=1, 
                      help="Âge approximatif du climatiseur en années")
frequence_entretien = st.selectbox("Fréquence d'entretien :", 
                                   options=["Annuel", "Tous les 2 ans", "Plus rare (> 2 ans)"], 
                                   index=0, help="Fréquence à laquelle le climatiseur est entretenu (nettoyage des filtres, révision, etc.)")
# Section 2: Paramètres d'utilisation et conditions météo
st.header("2. Paramètres d'utilisation et conditions météo")

# Sélection de la ville (toujours demandée pour contexte, même si saisie manuelle possible)
liste_villes = list(VILLES.keys())
ville_index_defaut = liste_villes.index("Tlemcen") if "Tlemcen" in liste_villes else 0
ville_choisie = st.selectbox("Ville :", options=liste_villes, index=ville_index_defaut)

# Paramètres d'utilisation de la climatisation
heures_utilisation = st.number_input("Nombre d'heures d'utilisation quotidienne :", 
                                     min_value=1, max_value=24, value=8, step=1)
surface = st.number_input("Surface de la pièce (en m²) :", min_value=5, max_value=500, value=20, step=1)
hauteur = st.number_input("Hauteur sous plafond (en m) :", min_value=2.0, max_value=5.0, value=2.5, step=0.1)
type_piece = st.selectbox("Type de pièce :", options=["Salon/Séjour", "Chambre", "Bureau", "Autre"], index=0)
presence_appareils = st.selectbox("Appareils électriques générant de la chaleur :", options=["Aucun", "Oui, quelques-uns", "Oui, plusieurs"], index=0)
type_vitrage = st.selectbox("Type de vitrage des fenêtres :", options=["Double vitrage", "Simple vitrage"], index=0)
orientation = st.selectbox("Orientation principale de la pièce :", options=["Nord", "Est", "Sud", "Ouest"], index=2)
nbr_personnes = st.number_input("Nombre de personnes habituellement présentes dans la pièce :", 
                                min_value=0, max_value=20, value=1, step=1)
temp_confort = st.number_input("Température de confort souhaitée (°C) :", 
                               min_value=16, max_value=30, value=24, step=1)

# Choix de la source des données météo (API ou saisie manuelle)
choix_source_meteo = st.radio("Source des données météo sur 7 jours :", 
                              options=["Données en ligne (OpenWeatherMap/Tameteo)", "Saisie manuelle"], index=0)

# Préparation des structures pour stocker les prévisions sur 7 jours (températures et humidité)
previsions_jours = []  # liste de dict pour 7 jours: {"Date":..., "Température (°C)":..., "Humidité (%)": ...}

# Si l'utilisateur choisit les données en ligne, on tente l'API OpenWeatherMap puis Tameteo en secours
if choix_source_meteo == "Données en ligne (OpenWeatherMap/Tameteo)":
    lat, lon = VILLES[ville_choisie]
    if OWM_API_KEY:
        # Appel de l'API OpenWeatherMap pour obtenir la météo actuelle et les prévisions quotidiennes
        try:
            # Météo actuelle
            url_current = (f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}"
                           f"&units=metric&lang=fr&appid={OWM_API_KEY}")
            res_current = requests.get(url_current)
            data_current = res_current.json() if res_current.status_code == 200 else {}
            # Prévisions quotidiennes sur 7 jours (OneCall API)
            url_onecall = (f"http://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}"
                           f"&exclude=minutely,hourly,alerts&units=metric&lang=fr&appid={OWM_API_KEY}")
            res_onecall = requests.get(url_onecall)
            data_onecall = res_onecall.json() if res_onecall.status_code == 200 else {}
        except Exception as e:
            st.error("Échec de la récupération des données météo via OpenWeatherMap.")
            data_current = {}
            data_onecall = {}

        # Traiter les données actuelles (affichage informatif)
        if data_current.get("weather"):
            desc = data_current["weather"][0]["description"].capitalize()
            temp_now = data_current["main"]["temp"]
            humid_now = data_current["main"].get("humidity")
            meteo_actuelle = f"{desc}, {temp_now:.1f} °C"
            if humid_now is not None:
                meteo_actuelle += f", Humidité {humid_now}%"
            st.write(f"**Météo actuelle à {ville_choisie} :** {meteo_actuelle}")
        else:
            st.write("Météo actuelle non disponible.")

        # Récupération des prévisions sur 7 jours à partir des données OneCall
        if data_onecall.get("daily"):
            try:
                for i, day in enumerate(data_onecall["daily"][:7]):  # limiter à 7 jours
                    # date du jour
                    dt_ts = day.get("dt", None)
                    if dt_ts:
                        # Conversion timestamp en date locale
                        date_locale = datetime.datetime.fromtimestamp(dt_ts)
                        date_str = date_locale.strftime("%d %b")  # ex: "28 Mar"
                    else:
                        date_str = f"Jour {i+1}"
                    # Température moyenne ou max du jour
                    # On peut prendre la température max et min du jour
                    temp_min = day.get("temp", {}).get("min")
                    temp_max = day.get("temp", {}).get("max")
                    if temp_min is not None and temp_max is not None:
                        # On utilise la moyenne (ou on pourrait garder min et max séparés)
                        temp_val = (temp_min + temp_max) / 2.0
                    else:
                        temp_val = day.get("temp", {}).get("day", None) or day.get("temp", None)
                    # Humidité relative moyenne du jour
                    humid_val = day.get("humidity", None)
                    previsions_jours.append({
                        "Date": date_str,
                        "Température (°C)": f"{temp_val:.1f}" if temp_val is not None else "",
                        "Humidité (%)": f"{humid_val:.0f}" if humid_val is not None else ""
                    })
            except Exception as e:
                previsions_jours = []
        else:
            # Si l'API OneCall n'a pas fonctionné, on tentera Tameteo
            previsions_jours = []

        # Si OpenWeatherMap a échoué à fournir les prévisions, on passe au plan B (Tameteo)
        if not previsions_jours:
            # Dictionnaire de correspondance ville -> ID Tameteo connu (extrait manuellement)
            tameteo_ids = {
                "Adrar": 8861,
                "Alger": 8842,
                "Annaba": 8849,
                "Batna": 8853,
                "Béchar": 8860,
                "Béjaïa": 8840,
                "Biskra": 8862,
                "Constantine": 8850,
                "Oran": 8859,
                "Tlemcen": 8858
            }
            tameteo_id = tameteo_ids.get(ville_choisie)
            if tameteo_id:
                tameteo_url = (f"https://www.tameteo.com/meteo_{ville_choisie.replace(' ', '+')}"
                               f"-Afrique-Algerie-Provincia+de+{ville_choisie.replace(' ', '+')}-1-{tameteo_id}.html")
                try:
                    res_tameteo = requests.get(tameteo_url)
                    res_tameteo.encoding = 'utf-8'
                    html = res_tameteo.text
                    # Extraire les 7 premiers jours (ligne commençant par "* " suivi du nom du jour)
                    # On cherche des motifs du type "Aujourd'hui", "Demain", ou les noms de jours avec température
                    days_data = []
                    for line in html.splitlines():
                        # Normaliser les espaces insécables et accents
                        segment = line.strip().replace("´", "'")
                        # Identifier les lignes de prévision journalière (commencent par une puce "* ")
                        if segment.startswith("* Aujourd'") or segment.startswith("* Demain") or segment.startswith("* Lundi") or segment.startswith("* Mardi") or segment.startswith("* Mercredi") or segment.startswith("* Jeudi") or segment.startswith("* Vendredi") or segment.startswith("* Samedi") or segment.startswith("* Dimanche"):
                            days_data.append(segment)
                        if len(days_data) >= 7:
                            break
                    # Parser chaque entrée pour en extraire temp max/min et (humidité non fournie, on mettra une valeur par défaut)
                    for entry in days_data[:7]:
                        # Exemple de segment : "* Aujourd'hui 28 Mars ... 18° / 7° ... 15 - 37 km/h"
                        parts = entry.split()
                        # Trouver les parties contenant "°" pour les températures
                        temps = [p for p in parts if "°" in p and "/" in p]
                        # Extraire temp max et min si possible
                        if temps:
                            # ex: "18°" et "7°" entourés de "/"
                            try:
                                max_temp = float(temps[0].replace("°", "").replace(",", "."))
                            except:
                                max_temp = None
                            try:
                                min_temp = float(temps[2].replace("°", "").replace(",", ".")) if len(temps) > 2 else None
                            except:
                                min_temp = None
                        else:
                            max_temp = min_temp = None
                        # Moyenne simple des deux si disponibles, sinon max_temp ou None
                        if max_temp is not None and min_temp is not None:
                            avg_temp = (max_temp + min_temp) / 2.0
                        else:
                            avg_temp = max_temp or min_temp
                        # Utiliser une humidité par défaut (50%) car tameteo ne la fournit pas directement dans ce résumé
                        avg_humid = 50
                        # Récupérer le nom du jour et la date pour affichage
                        # On prend les deux ou trois premiers mots (ex: "* Aujourd'hui 28 Mars" -> "Aujourd'hui 28 Mar")
                        jour_str = " ".join(parts[1:4]) if parts[0] == "*" else " ".join(parts[0:3])
                        previsions_jours.append({
                            "Date": jour_str.strip("* "),
                            "Température (°C)": f"{avg_temp:.1f}" if avg_temp is not None else "",
                            "Humidité (%)": f"{avg_humid:.0f}"
                        })
                except Exception as e:
                    st.error("Échec de la récupération des prévisions via Tameteo.")
            else:
                st.error("Ville non prise en charge pour les prévisions Tameteo.")
    else:
        st.warning("Clé API OpenWeatherMap non fournie. Veuillez saisir la météo manuellement.")
# Si l'utilisateur choisit de saisir manuellement la météo sur 7 jours
if choix_source_meteo == "Saisie manuelle":
    st.write("**Entrez les prévisions météo manuellement pour les 7 prochains jours :**")
    # Suggestion : date de début = aujourd'hui
    date_debut = datetime.date.today()
    manuel_data = []
    # Formulaire sous forme de colonnes pour chaque jour
    for i in range(7):
        jour_date = date_debut + datetime.timedelta(days=i)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(jour_date.strftime("%A %d %b").capitalize())  # ex: "Vendredi 28 Mar"
        with col2:
            t = st.number_input(f"Temp. Jour {i+1} (°C)", value=25.0, key=f"temp_manuel_{i}")
        with col3:
            h = st.number_input(f"Humidité Jour {i+1} (%)", min_value=0, max_value=100, value=50, key=f"hum_manuel_{i}")
        manuel_data.append((t, h))
    # Proposition d'import d'un fichier Excel pour remplir ces données
    modele_xlsx = pd.DataFrame({
        "Jour": [f"Jour {j+1}" for j in range(7)],
        "Température (°C)": [25.0]*7,
        "Humidité (%)": [50]*7
    })
    # Permettre à l'utilisateur de télécharger un modèle d'Excel
    st.download_button("Télécharger un modèle Excel", data=modele_xlsx.to_csv(index=False).encode('utf-8'),
                       file_name="modele_meteo7j.csv", mime="text/csv")
    fichier_excel = st.file_uploader("Ou importez un fichier Excel (.xlsx) avec 7 jours de données météo :", type=["xlsx"])
    if fichier_excel:
        try:
            # Lire le fichier Excel (on suppose qu'il contient au moins deux colonnes: Température, Humidité)
            xl = pd.read_excel(fichier_excel)
            for i in range(min(7, len(xl))):
                temp_val = xl.iloc[i][1] if xl.shape[1] > 1 else None
                hum_val = xl.iloc[i][2] if xl.shape[1] > 2 else None
                if pd.notna(temp_val):
                    manuel_data[i] = (float(temp_val), manuel_data[i][1])
                if pd.notna(hum_val):
                    manuel_data[i] = (manuel_data[i][0], int(hum_val))
        except Exception as e:
            st.error("Échec de la lecture du fichier Excel. Veuillez vérifier le format.")
    # Remplir previsions_jours à partir des données manuelles (manuel_data)
    for i, (t, h) in enumerate(manuel_data):
        date_label = (date_debut + datetime.timedelta(days=i)).strftime("%d %b")
        previsions_jours.append({
            "Date": date_label,
            "Température (°C)": f"{t:.1f}",
            "Humidité (%)": f"{h:.0f}"
        })

# Afficher un tableau récapitulatif des prévisions météo sur 7 jours utilisées
if previsions_jours:
    st.subheader(f"Prévisions météo sur 7 jours - {ville_choisie}")
    st.table(previsions_jours)
else:
    st.error("Aucune donnée météo disponible. Des valeurs par défaut seront utilisées pour la simulation.")
# Section 3: Simulation de la consommation sur 7 jours (Scénario normal vs optimisé)
st.header("3. Simulation de la consommation : Scénario normal vs optimisé")

# Bouton pour lancer la simulation
if st.button("Lancer la simulation"):
    # Vérification que les caractéristiques du climatiseur sont bien renseignées
    if not st.session_state.get("ac_data_ok", False):
        st.error("Veuillez d'abord renseigner les caractéristiques du climatiseur en section 1.")
    else:
        # Récupérer les données du climatiseur depuis l'état de session
        consommation_kw = st.session_state.get("ac_conso", 1.0)  # puissance électrique (kW)
        puissance_frigo_kw = st.session_state.get("ac_froid", 2.0)  # puissance frigorifique (kW)
        est_inverter = st.session_state.get("ac_inverter", True)

        # Préparation des résultats sur 7 jours
        consommation_journaliere_normale = []
        consommation_journaliere_optimisee = []

        # On définit un profil d'utilisation horaire sur 24h en fonction du nombre d'heures d'utilisation
        heures_totales = 24
        # Nombre d'heures d'utilisation dans la journée (X)
        X = int(heures_utilisation)
        if X > heures_totales:
            X = heures_totales
        # Plage horaire d'utilisation (par défaut, on aligne sur le milieu de journée pour usage <=12h, ou toute la journée si >12h)
        if X <= 12:
            # On centre la plage d'utilisation autour de 15h (pic de chaleur vers milieu d'après-midi)
            center = 15
            start_hour = max(0, center - math.floor(X/2))
            end_hour = start_hour + X - 1
            if end_hour > 23:
                end_hour = 23
                start_hour = end_hour - X + 1
        else:
            # Si utilisation très longue (>12h), on la fait s'étendre jusqu'à la fin de la journée
            start_hour = max(0, heures_totales - X)
            end_hour = 23

        # Pour chaque jour de la période de 7 jours, calculer la consommation
        for jour_index in range(7):
            # Obtenir les conditions météo du jour (températures sur 24h)
            # Si on a des prévisions_jours remplies, on utilise les valeurs, sinon on met des valeurs par défaut
            if jour_index < len(previsions_jours):
                try:
                    # Convertir la température moyenne du jour en min et max estimés
                    t_day = float(previsions_jours[jour_index]["Température (°C)"])
                    # On suppose un écart jour/nuit de +/-5°C autour de cette moyenne pour simuler une courbe
                    t_min = t_day - 5
                    t_max = t_day + 5
                except:
                    # Valeurs par défaut si parsing impossible
                    t_min = 20.0
                    t_max = 30.0
                try:
                    humid_day = float(previsions_jours[jour_index]["Humidité (%)"])
                except:
                    humid_day = 50.0
            else:
                # Valeurs par défaut si pas de données pour ce jour
                t_min = 20.0
                t_max = 30.0
                humid_day = 50.0

            # Génération d'une courbe de température extérieure estimée sur 24h (simple modèle triangulaire jour/nuit)
            outside_temps = [0.0] * heures_totales
            for h in range(heures_totales):
                if h < 6:
                    # nuit tôt
                    outside_temps[h] = t_min
                elif 6 <= h <= 15:
                    # montée de température le jour
                    outside_temps[h] = t_min + (t_max - t_min) * ((h - 6) / (15 - 6))
                else:
                    # redescente en fin de journée
                    outside_temps[h] = t_max - (t_max - t_min) * ((h - 15) / (24 - 15))

            # Listes de consommation horaire pour ce jour, pour chaque scénario
            conso_horaire_normale = [0.0] * heures_totales
            conso_horaire_optimisee = [0.0] * heures_totales

            for h in range(heures_totales):
                if start_hour <= h <= end_hour:
                    # SCÉNARIO NORMAL : climatiseur allumé en continu pendant toute la période d'occupation
                    conso_horaire_normale[h] = consommation_kw  # consommation pleine puissance

                    # SCÉNARIO OPTIMISÉ : modulation de la puissance en fonction des besoins
                    # Calcul de l'écart de température extérieur vs confort
                    temp_ext = outside_temps[h]
                    diff = max(0.0, temp_ext - temp_confort)
                    # Ajustement en fonction de l'isolation thermique (déjà pris via diff? Non, on applique sur diff)
                    # (Niveau d'isolation initial: "Moyenne" considéré neutre, "Bonne" réduit les besoins, "Faible" les augmente)
                    niveau_iso = isolation if 'isolation' in locals() else "Moyenne"
                    if niveau_iso == "Bonne":
                        diff *= 0.8
                    elif niveau_iso == "Faible":
                        diff *= 1.2
                    # Ajustement en fonction du vitrage (simple vitrage = plus de pertes, double = moins)
                    if type_vitrage == "Simple vitrage":
                        diff *= 1.1
                    else:
                        # Double vitrage (on considère baseline en double, donc pas de réduction majeure, juste neutre ou légère amélioration)
                        diff *= 0.95

                    # Impact de l'orientation sur le gain solaire aux heures chaudes
                    # On applique un facteur d'ensoleillement supplémentaire sur diff aux heures concernées selon orientation
                    if 10 <= h <= 16:  # plage approximative de fort ensoleillement
                        if orientation == "Sud":
                            diff *= 1.1  # plein sud reçoit beaucoup de soleil la journée
                        elif orientation == "Ouest":
                            # Ouest surtout l'après-midi (mettons 12h-18h, on est dans 10-16 donc partiel)
                            diff *= 1.1
                        elif orientation == "Est":
                            # Est surtout le matin (6h-12h), à 10-16h l'effet est moins fort, on peut mettre un léger facteur
                            diff *= 1.05
                        elif orientation == "Nord":
                            # Nord a très peu de soleil direct, on peut même réduire un peu le diff car moins de charge solaire
                            diff *= 0.95

                    # Présence d'appareils émettant de la chaleur (TV, PC, etc.)
                    if presence_appareils == "Oui, quelques-uns":
                        diff *= 1.1  # quelques appareils -> +10% charge thermique
                    elif presence_appareils == "Oui, plusieurs":
                        diff *= 1.2  # plusieurs appareils -> +20%

                    # Impact du nombre de personnes (chaleur humaine) : +5% de charge par personne supplémentaire au-delà de 1
                    diff *= (1 + 0.05 * max(0, nbr_personnes - 1))

                    # Ajustement pour hauteur sous plafond : on considère base 2.5m, si plus haut -> volume plus grand à refroidir
                    if hauteur and hauteur > 0:
                        diff *= (hauteur / 2.5)

                    # Effet de l'humidité : au-delà de 50% d'humidité, la clim doit travailler plus (déshumidification)
                    if humid_day and humid_day > 50:
                        surplus_humid_factor = 1 + 0.001 * (humid_day - 50)  # +0.1% de charge par % au-dessus de 50
                        diff *= surplus_humid_factor

                    # Calcul d'un facteur de fonctionnement de la clim (0 à 1) basé sur l'écart de température modifié
                    # Supposons qu'un écart de 10°C ou plus nécessite 100% de la puissance de la clim
                    facteur_utilisation = diff / 10.0
                    if facteur_utilisation > 1:
                        facteur_utilisation = 1.0
                    if facteur_utilisation < 0:
                        facteur_utilisation = 0.0

                    # Prise en compte de la technologie inverter : un inverter est plus efficace à charge partielle, donc consomme un peu moins
                    if est_inverter:
                        facteur_utilisation *= 0.95  # 5% de consommation en moins grâce à l'inverter
                    else:
                        facteur_utilisation *= 1.05  # non-inverter peut consommer ~5% de plus pour le même refroidissement

                    # Climatiseur ancien ou mal entretenu : efficacité réduite -> consommation accrue
                    # On applique un facteur d'inefficacité basé sur l'âge et la fréquence d'entretien
                    inefficacite = 1.0
                    # Par exemple, +1% de consommation par année d'âge (max +20% à 20 ans, par cap)
                    inefficacite *= (1 + 0.01 * min(age, 20))
                    # Fréquence d'entretien : plus c'est rare, plus la conso augmente (on majore de 5 à 10%)
                    if frequence_entretien == "Tous les 2 ans":
                        inefficacite *= 1.05
                    elif frequence_entretien == "Plus rare (> 2 ans)":
                        inefficacite *= 1.10
                    facteur_utilisation *= inefficacite

                    # Assurer que le facteur ne dépasse pas 1 (100% de la puissance max)
                    if facteur_utilisation > 1:
                        facteur_utilisation = 1.0

                    # Consommation optimisée à cette heure (kW * fraction du temps)
                    conso_horaire_optimisee[h] = consommation_kw * facteur_utilisation
                else:
                    # En dehors des heures d'utilisation, le climatiseur est éteint dans les deux scénarios
                    conso_horaire_normale[h] = 0.0
                    conso_horaire_optimisee[h] = 0.0

            # Calcul de la consommation totale du jour (kWh)
            total_kwh_normal = sum(conso_horaire_normale)
            total_kwh_optimise = sum(conso_horaire_optimisee)
            consommation_journaliere_normale.append(total_kwh_normal)
            consommation_journaliere_optimisee.append(total_kwh_optimise)

        # Une fois les 7 jours simulés, calculer les coûts et économies
        couts_normaux = [kwh * TARIF_ELECTRICITE for kwh in consommation_journaliere_normale]
        couts_optimises = [kwh * TARIF_ELECTRICITE for kwh in consommation_journaliere_optimisee]

        # Affichage des résultats chiffrés pour chaque jour
        st.subheader("Résultats de la simulation sur 7 jours :")
        for j in range(len(consommation_journaliere_normale)):
            jour_label = previsions_jours[j]["Date"] if j < len(previsions_jours) else f"Jour {j+1}"
            st.write(f"**{jour_label}** – Consommation normale : {consommation_journaliere_normale[j]:.1f} kWh "
                     f"(coût {couts_normaux[j]:.0f} DZD), "
                     f"optimisée : {consommation_journaliere_optimisee[j]:.1f} kWh "
                     f"(coût {couts_optimises[j]:.0f} DZD)")

        # Calcul des économies totales sur la semaine
        total_kwh_normal_sem = sum(consommation_journaliere_normale)
        total_kwh_optimise_sem = sum(consommation_journaliere_optimisee)
        economie_kwh_total = total_kwh_normal_sem - total_kwh_optimise_sem
        economie_pourcent_total = (economie_kwh_total / total_kwh_normal_sem * 100) if total_kwh_normal_sem > 0 else 0.0
        economie_cout_total = economie_kwh_total * TARIF_ELECTRICITE
        st.write(f"**Économies totales sur 7 jours** : {economie_kwh_total:.1f} kWh économisés, soit {economie_pourcent_total:.0f}% de moins qu'une utilisation normale, représentant environ {economie_cout_total:.0f} DZD.")

        # Graphique 1 : Profil horaire de consommation (pour le premier jour simulé à titre d'exemple)
        st.subheader("Profil horaire de consommation (Jour 1)")
        if consommation_journaliere_normale:
            heures = list(range(24))
            df_horaire = pd.DataFrame({
                "Heure": heures,
                "Consommation normale (kW)": conso_horaire_normale,    # du dernier jour calculé ou du jour 1? Ici c'est le dernier calculé dans boucle
                "Consommation optimisée (kW)": conso_horaire_optimisee
            })
            df_horaire = df_horaire.set_index("Heure")
            st.line_chart(df_horaire)  # affichage simple du profil 24h du dernier jour simulé
        else:
            st.write("Aucune donnée horaire à afficher.")

        # Graphique 2 : Comparaison de la consommation quotidienne sur les 7 jours
        st.subheader("Consommation quotidienne sur 7 jours")
        jours = [previsions_jours[j]["Date"] if j < len(previsions_jours) else f"Jour {j+1}" for j in range(7)]
        data_chart = []
        for j, jour_label in enumerate(jours):
            # Ajout de deux entrées par jour (normal et optimisé) pour le graphique groupé
            val_norm = consommation_journaliere_normale[j] if j < len(consommation_journaliere_normale) else 0.0
            val_opti = consommation_journaliere_optimisee[j] if j < len(consommation_journaliere_optimisee) else 0.0
            data_chart.append({"Jour": jour_label, "Scénario": "Normal", "Consommation (kWh)": val_norm})
            data_chart.append({"Jour": jour_label, "Scénario": "Optimisé", "Consommation (kWh)": val_opti})
        df_chart = pd.DataFrame(data_chart)
        # Création d'un graphique Altair en barres groupées
        chart = alt.Chart(df_chart).mark_bar().encode(
            x=alt.X("Jour:N", title="Jour"),
            y=alt.Y("Consommation (kWh):Q", title="Consommation (kWh)"),
            color="Scénario:N",
            xOffset="Scénario:N"
        ).properties(width=600)
        st.altair_chart(chart, use_container_width=True)

        # Marquer que la simulation a été effectuée, pour débloquer le chat IA
        st.session_state["simulation_effectuee"] = True
        # Réinitialiser l'autorisation de chat pour cette simulation
        st.session_state["chat_utilise"] = False
        st.session_state["derniere_reponse_ia"] = ""
# Section 4: Rapport d'analyse automatique par IA DeepSeek
st.header("4. Rapport d'analyse par IA")

if DEEPSEEK_API_KEY:
    if st.session_state.get("simulation_effectuee", False):
        try:
            # Préparation de la requête à l'IA DeepSeek pour obtenir un rapport personnalisé
            rapport_prompt = (
                "Vous êtes un expert en efficacité énergétique. Analysez les résultats de la simulation suivants pour un climatiseur domestique et fournissez un rapport :\n"
                f"- Modèle du climatiseur : {st.session_state.get('ac_modele', 'N/A')}\n"
                f"- Inverter : {'oui' if est_inverter else 'non'}\n"
                f"- Puissance frigorifique : {puissance_frigo_kw} kW\n"
                f"- Consommation électrique : {consommation_kw} kW\n"
                f"- Ville : {ville_choisie}\n"
                f"- Type de pièce : {type_piece}\n"
                f"- Surface : {surface} m², Hauteur : {hauteur} m\n"
                f"- Isolation : {st.session_state.get('isolation', 'Moyenne')}\n"
                f"- Vitrage : {type_vitrage}\n"
                f"- Orientation : {orientation}\n"
                f"- Appareils supplémentaires : {presence_appareils}\n"
                f"- Nombre de personnes : {nbr_personnes}\n"
                f"- Température de confort : {temp_confort} °C\n"
                f"- Heures d'utilisation par jour : {X} h\n"
                f"- Consommation journalière scénario normal : {consommation_journaliere_normale[0]:.1f} kWh (jour 1)\n"
                f"- Consommation journalière scénario optimisé : {consommation_journaliere_optimisee[0]:.1f} kWh (jour 1)\n"
                f"- Économies réalisées sur 7 jours : {economie_kwh_total:.1f} kWh, soit {economie_pourcent_total:.0f}% de réduction ({economie_cout_total:.0f} DZD économisés)\n\n"
                "Rédigez un rapport concis commentant ces résultats, en soulignant les économies d'énergie possibles. Incluez des conseils pertinents (par ex. impact de l'isolation, de l'âge de l'appareil, de l'entretien, etc.)."
            )
            # Appel à l'API DeepSeek pour générer le rapport
            rapport_response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": rapport_prompt}],
                temperature=0.2,
                max_tokens=1024
            )
            rapport_texte = rapport_response["choices"][0]["message"]["content"]
            st.write(rapport_texte)
        except Exception as e:
            st.error("Erreur lors de la génération du rapport par l'IA DeepSeek.")
    else:
        st.info("Veuillez lancer la simulation ci-dessus pour générer le rapport d'analyse.")
else:
    st.info("Clé API DeepSeek manquante. Configurez la pour obtenir un rapport d'analyse automatique.")
# Section 5: Chat IA (question/réponse après la simulation)
st.header("5. Chat IA (après simulation)")

if DEEPSEEK_API_KEY:
    if st.session_state.get("simulation_effectuee", False):
        # Proposer une question automatique (affichée mais non envoyée automatiquement)
        question_suggestion = "Quels autres conseils pour réduire la consommation de mon climatiseur ?"
        st.write(f"*Suggestion de question à poser à l'IA :* **{question_suggestion}**")

        # Champ de texte pour la question utilisateur
        question_user = st.text_input("Votre question pour l'IA (vous pouvez poser une seule question par simulation) :")
        if st.button("Envoyer la question"):
            if st.session_state.get("chat_utilise", False):
                st.warning("Vous avez déjà posé une question pour cette simulation. Relancez une nouvelle simulation pour poser une autre question.")
            elif question_user.strip() == "":
                st.warning("Veuillez saisir une question avant d'envoyer.")
            else:
                try:
                    # Construire le message avec contexte + question de l'utilisateur
                    contexte = (
                        f"Modèle: {st.session_state.get('ac_modele', 'N/A')}, "
                        f"Inverter: {'oui' if est_inverter else 'non'}, "
                        f"Puissance: {puissance_frigo_kw} kW, Consommation: {consommation_kw} kW, "
                        f"Âge: {age} ans, Entretien: {frequence_entretien}, "
                        f"Pièce: {type_piece}, Surface: {surface} m², Hauteur: {hauteur} m, Orientation: {orientation}, Vitrage: {type_vitrage}, "
                        f"Appareils: {presence_appareils}, Personnes: {nbr_personnes}, "
                        f"Température de confort: {temp_confort} °C, "
                        f"Consommation normale (jour 1): {consommation_journaliere_normale[0]:.1f} kWh, "
                        f"Consommation optimisée (jour 1): {consommation_journaliere_optimisee[0]:.1f} kWh, "
                        f"Économies 7j: {economie_kwh_total:.1f} kWh soit {economie_pourcent_total:.0f}%."
                    )
                    messages = [
                        {"role": "system", "content": "Vous êtes un assistant énergétique qui aide l'utilisateur à optimiser la consommation de son climatiseur. Le contexte de la simulation est fourni."},
                        {"role": "user", "content": f"Contexte: {contexte}\nQuestion: {question_user}"}
                    ]
                    response = openai.ChatCompletion.create(
                        model="deepseek-chat",
                        messages=messages,
                        temperature=0.3,
                        max_tokens=512
                    )
                    reponse_ia = response["choices"][0]["message"]["content"]
                    # Afficher la réponse de l'IA
                    st.write("**Réponse de l'IA :**")
                    st.write(reponse_ia)
                    # Marquer le chat comme utilisé pour cette simulation
                    st.session_state["chat_utilise"] = True
                    st.session_state["derniere_reponse_ia"] = reponse_ia
                except Exception as e:
                    st.error("Erreur lors de la communication avec l'IA DeepSeek.")
        # Si l'utilisateur a déjà posé sa question, on empêche une autre question
        if st.session_state.get("chat_utilise", False):
            st.info("Vous avez posé une question. Pour poser une autre question, veuillez relancer une nouvelle simulation.")
    else:
        st.info("Lancez d'abord la simulation ci-dessus pour pouvoir discuter avec l'IA.")
else:
    st.info("Clé API DeepSeek manquante. Le chat IA n'est pas disponible.")
