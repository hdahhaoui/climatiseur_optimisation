import streamlit as st
import requests
import datetime
import math

# Configuration de l'API (clés à fournir dans les secrets de l'application Streamlit)
DEEPSEEK_API_KEY = st.secrets.get("sk-c2463319fd4d461d9172e8b5b49936dd", None)
OWM_API_KEY = st.secrets.get("420227af9037639d0d68ac9deafead1a", None)

# Tarif de l'électricité (DZD par kWh)
TARIF_ELECTRICITE = 5  # 5 DZD/kWh (tarif fixe)

# Liste prédéfinie de 16 villes algériennes avec leurs coordonnées (latitude, longitude)
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
st.title("Simulation de consommation énergétique d'un climatiseur")

# Section 1: Introduction du modèle de climatiseur et récupération des données techniques via DeepSeek
st.header("1. Caractéristiques du climatiseur")

# Champ de texte pour entrer le modèle du climatiseur
modele = st.text_input("Modèle du climatiseur :", value="", help="Entrez la référence exacte du climatiseur (ex: Marque Modèle 1234)")

# Bouton pour interroger l'API DeepSeek avec le modèle saisi
deepseek_result = None
if st.button("Obtenir les données techniques via l'IA DeepSeek"):
    if DEEPSEEK_API_KEY:
        # Préparation de la requête à l'API DeepSeek (format compatible OpenAI)
        import openai
        openai.api_base = "https://api.deepseek.com/v1"
        openai.api_key = DEEPSEEK_API_KEY
        # Formulation de la demande pour obtenir les caractéristiques du climatiseur
        prompt = f"Fournis les caractéristiques techniques du climatiseur {modele} : consommation électrique (en kW), puissance frigorifique (en kW) et préciser s'il s'agit d'un modèle inverter ou non."
        try:
            response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            deepseek_text = response["choices"][0]["message"]["content"]
            # Extraction basique des données depuis la réponse texte de l'IA
            # On cherche des nombres dans le texte pour consommation et puissance, et les mots "inverter" ou "non-inverter"
            conso_val = None
            froid_val = None
            inverter_val = None
            # Parcours du texte pour trouver des chiffres (kW) et le mot inverter
            import re
            # Chercher consommation électrique en kW
            match_conso = re.search(r'consommation.*?([\d\.]+)\s*kW', deepseek_text, re.IGNORECASE)
            if match_conso:
                conso_val = float(match_conso.group(1))
            # Chercher puissance frigorifique en kW ou BTU (convertir BTU en kW si nécessaire)
            match_froid = re.search(r'puissance frigorifique.*?([\d\.]+)\s*kW', deepseek_text, re.IGNORECASE)
            if match_froid:
                froid_val = float(match_froid.group(1))
            else:
                match_froid_btu = re.search(r'puissance frigorifique.*?([\d\,]+)\s*BTU', deepseek_text, re.IGNORECASE)
                if match_froid_btu:
                    try:
                        btu_val = float(match_froid_btu.group(1).replace(',', ''))
                        froid_val = round(btu_val * 0.00029307107, 2)  # conversion BTU/h -> kW
                    except:
                        froid_val = None
            # Chercher mention inverter
            if re.search(r'inverter', deepseek_text, re.IGNORECASE):
                # Si le texte contient "non inverter" explicitement
                if re.search(r'non inverter', deepseek_text, re.IGNORECASE) or re.search(r"pas inverter", deepseek_text, re.IGNORECASE):
                    inverter_val = False
                else:
                    inverter_val = True
            # Stocker les résultats partiels dans l'état de session
            st.session_state["ac_modele"] = modele
            st.session_state["ac_conso"] = conso_val
            st.session_state["ac_froid"] = froid_val
            st.session_state["ac_inverter"] = inverter_val
            # Indiquer si DeepSeek a réussi à fournir des données complètes
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

# Si DeepSeek a échoué ou n'a pas fourni toutes les infos, on affiche le formulaire manuel
if "ac_data_ok" in st.session_state and st.session_state["ac_data_ok"] == False:
    st.write("**Veuillez renseigner manuellement les caractéristiques du climatiseur :**")
    # Champs manuels pour consommation, puissance et inverter
    # Si DeepSeek a renvoyé partiellement des infos, on pré-remplit les champs correspondants
    conso_def = st.session_state.get("ac_conso", None)
    froid_def = st.session_state.get("ac_froid", None)
    inverter_def = st.session_state.get("ac_inverter", None)
    if conso_def is None:
        conso_def = 1.0  # valeur par défaut 1 kW si inconnue
    if froid_def is None:
        froid_def = 3.5  # par défaut 3.5 kW (~12000 BTU) si inconnue
    # Interface du formulaire manuel
    conso_input = st.number_input("Consommation électrique (kW) :", min_value=0.1, max_value=10.0, value=float(conso_def), step=0.1)
    froid_input = st.number_input("Puissance frigorifique (kW) :", min_value=0.5, max_value=20.0, value=float(froid_def), step=0.1)
    inverter_input = st.radio("Technologie inverter :", options=["Oui", "Non"], index=(0 if inverter_def else 1) if inverter_def is not None else 0)
    # Convertir le choix radio en booléen
    inverter_bool = True if inverter_input == "Oui" else False
    # Bouton pour valider les données manuelles
    if st.button("Valider les données du climatiseur"):
        st.session_state["ac_modele"] = modele or "Modèle inconnu"
        st.session_state["ac_conso"] = float(conso_input)
        st.session_state["ac_froid"] = float(froid_input)
        st.session_state["ac_inverter"] = inverter_bool
        st.session_state["ac_data_ok"] = True

# Si on a des données complètes (via DeepSeek ou formulaire), afficher le résumé des caractéristiques techniques
if st.session_state.get("ac_data_ok", False):
    st.success("Caractéristiques du climatiseur prêtes.")
    # Récupération des données depuis l'état de session
    modele_confirme = st.session_state.get("ac_modele", "N/A")
    conso_confirme = st.session_state.get("ac_conso", None)
    froid_confirme = st.session_state.get("ac_froid", None)
    inverter_confirme = st.session_state.get("ac_inverter", None)
    # Affichage du résumé
    st.subheader("Résumé des caractéristiques techniques :")
    st.write(f"- **Modèle** : {modele_confirme}")
    if conso_confirme is not None:
        st.write(f"- **Consommation électrique** : {conso_confirme} kW")
    if froid_confirme is not None:
        st.write(f"- **Puissance frigorifique** : {froid_confirme} kW")
    if inverter_confirme is not None:
        st.write(f"- **Technologie inverter** : {'Oui' if inverter_confirme else 'Non'}")
# Section 2: Paramètres d'utilisation et météo
st.header("2. Paramètres d'utilisation et conditions météo")

# Sélection de la ville
liste_villes = list(VILLES.keys())
ville_index_defaut = liste_villes.index("Tlemcen") if "Tlemcen" in liste_villes else 0
ville_choisie = st.selectbox("Ville :", options=liste_villes, index=ville_index_defaut)
lat, lon = VILLES[ville_choisie]

# Nombre d'heures d'utilisation quotidienne
heures_utilisation = st.number_input("Nombre d'heures d'utilisation quotidienne :", min_value=1, max_value=24, value=8, step=1)

# Surface de la pièce (m²)
surface = st.number_input("Surface de la pièce (en m²) :", min_value=5, max_value=200, value=20, step=1)

# Niveau d'isolation
isolation = st.selectbox("Niveau d'isolation de la pièce :", options=["Bonne", "Moyenne", "Faible"], index=1)

# Présence de fenêtres exposées au soleil
fenetres_soleil = st.selectbox("Fenêtres exposées au soleil :", options=["Oui", "Non"], index=1)
fenetres_soleil_bool = (fenetres_soleil == "Oui")

# Nombre de personnes dans la pièce
personnes = st.number_input("Nombre de personnes présentes dans la pièce :", min_value=1, max_value=20, value=1, step=1)

# Température de confort souhaitée (°C)
temp_confort = st.number_input("Température de confort souhaitée (°C) :", min_value=16, max_value=30, value=24, step=1)

# Affichage de la météo actuelle et prévisions à 14 jours pour la ville sélectionnée
st.subheader(f"Météo à {ville_choisie}")

meteo_actuelle = None
previsions_jours = None
if OWM_API_KEY:
    try:
        # Appel API OpenWeatherMap pour la météo actuelle
        url_current = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&lang=fr&appid={OWM_API_KEY}"
        res_current = requests.get(url_current)
        data_current = res_current.json() if res_current.status_code == 200 else {}
        # Appel API pour les prévisions quotidiennes sur 14 jours
        url_daily = f"http://api.openweathermap.org/data/2.5/forecast/daily?lat={lat}&lon={lon}&cnt=14&units=metric&lang=fr&appid={OWM_API_KEY}"
        res_daily = requests.get(url_daily)
        data_daily = res_daily.json() if res_daily.status_code == 200 else {}
        # Appel API OneCall pour obtenir des prévisions horaires (48h) plus précises
        url_onecall = f"http://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude=minutely,alerts&units=metric&lang=fr&appid={OWM_API_KEY}"
        res_onecall = requests.get(url_onecall)
        data_onecall = res_onecall.json() if res_onecall.status_code == 200 else {}
    except Exception as e:
        st.error("Échec de la récupération des données météo.")
        data_current = {}
        data_daily = {}
        data_onecall = {}

    # Traiter la météo actuelle
    if data_current.get("weather"):
        desc = data_current["weather"][0]["description"].capitalize()
        temp_now = data_current["main"]["temp"]
        humid = data_current["main"].get("humidity", None)
        meteo_actuelle = f"{desc}, {temp_now:.1f} °C"
        if humid is not None:
            meteo_actuelle += f", Humidité {humid}%"
        st.write(f"**Météo actuelle** : {meteo_actuelle}")
    else:
        st.write("Météo actuelle non disponible.")

    # Traiter les prévisions sur 14 jours
    if data_daily.get("list"):
        previsions_jours = []
        timezone_offset = 0
        if "city" in data_daily and "timezone" in data_daily["city"]:
            timezone_offset = data_daily["city"]["timezone"]
        for entry in data_daily["list"]:
            dt_ts = entry.get("dt")
            if dt_ts:
                # Convertir le timestamp en date locale
                date_locale = datetime.datetime.utcfromtimestamp(dt_ts + timezone_offset)
                date_str = date_locale.strftime("%d %b")
            else:
                date_str = "N/A"
            temp_min = entry.get("temp", {}).get("min")
            temp_max = entry.get("temp", {}).get("max")
            desc_day = entry.get("weather", [{}])[0].get("description", "")
            previsions_jours.append({
                "Date": date_str,
                "Min (°C)": f"{temp_min:.1f}" if temp_min is not None else "",
                "Max (°C)": f"{temp_max:.1f}" if temp_max is not None else "",
                "Temps": desc_day
            })
        # Afficher la table des prévisions (14 jours)
        st.write("**Prévisions 14 jours :**")
        st.table(previsions_jours)
    else:
        st.write("Prévisions 14 jours non disponibles.")
else:
    st.warning("Clé API OpenWeatherMap non fournie. Impossible d'afficher les données météo.")

# Analyse automatique des heures optimales d'utilisation sur la base de la météo (recommandations)
st.subheader("Recommandations d'utilisation optimisée")
if previsions_jours:
    # On utilise le premier jour de la liste pour baser nos conseils (jour actuel ou prochain)
    premier_jour = previsions_jours[0]
    try:
        max_temp = float(premier_jour["Max (°C)"])
        min_temp = float(premier_jour["Min (°C)"])
    except:
        max_temp = None
        min_temp = None
    if max_temp is not None and max_temp >= 32:
        st.info("**Conseil :** Évitez d'utiliser la climatisation entre **13h et 16h** car il fera très chaud à ce moment-là.")
    elif max_temp is not None and max_temp >= 25:
        st.info("**Conseil :** Limitez l'utilisation aux heures les moins chaudes de la journée (matinée ou fin d'après-midi) pour économiser de l'énergie.")
    if min_temp is not None and min_temp < temp_confort:
        st.info("**Conseil :** Profitez de la fraîcheur en début de journée en **laissant les fenêtres ouvertes le matin** pour refroidir la pièce naturellement.")
    elif min_temp is not None and min_temp < 20:
        st.info("**Conseil :** La nuit sera plus fraîche, pensez à aérer la pièce tard le soir ou tôt le matin pour réduire le besoin de climatisation.")
else:
    st.write("Aucun conseil disponible sans données météo.")

# Section 3: Simulation des deux scénarios (normal vs optimisé)
st.header("3. Simulation de la consommation : Scénario normal vs optimisé")

# Bouton pour lancer la simulation
if st.button("Lancer la simulation"):
    # Vérifier que les caractéristiques du climatiseur sont disponibles
    if not st.session_state.get("ac_data_ok", False):
        st.error("Veuillez d'abord renseigner les caractéristiques du climatiseur (section 1).")
    else:
        # Récupérer les données du climatiseur
        consommation_kw = st.session_state.get("ac_conso", 1.0)  # puissance électrique en kW
        puissance_frigo_kw = st.session_state.get("ac_froid", 2.0)  # puissance frigorifique en kW
        est_inverter = st.session_state.get("ac_inverter", True)

        # Préparation des variables de simulation
        heures_totales = 24
        # Déterminer la plage horaire d'occupation (scénario normal : climatiseur allumé toute la période d'occupation)
        X = int(heures_utilisation)
        if X > heures_totales:
            X = heures_totales
        start_hour = 0
        end_hour = heures_totales - 1
        if X <= 12:
            # On centre la plage d'utilisation autour de 15h (pic de chaleur vers milieu de journée)
            center = 15
            start_hour = max(0, center - math.floor(X/2))
            end_hour = start_hour + X - 1
            if end_hour > 23:
                end_hour = 23
                start_hour = end_hour - X + 1
        else:
            # Si l'occupation est longue (>12h), on la fait s'étendre jusqu'à la fin de la journée
            start_hour = max(0, heures_totales - X)
            end_hour = 23

        # Récupérer les prévisions horaires sur les 24 prochaines heures (si disponibles)
        outside_temps = [None] * heures_totales
        if OWM_API_KEY and 'data_onecall' in locals() and data_onecall.get("hourly"):
            # Utiliser les 24 premières heures de data_onecall
            for i in range(min(24, len(data_onecall["hourly"]))):
                outside_temps[i] = data_onecall["hourly"][i]["temp"]
            # S'il manque des heures, on tente de compléter avec min/max journaliers de data_daily
            if None in outside_temps and data_daily.get("list"):
                # Utiliser une interpolation simple basée sur les temp min/max du jour
                if data_daily["list"]:
                    day_info = data_daily["list"][0]
                    t_min = day_info.get("temp", {}).get("min", temp_confort)
                    t_max = day_info.get("temp", {}).get("max", temp_confort)
                    # Approximation : min à 6h, max à 15h, forme triangulaire
                    for h in range(heures_totales):
                        if outside_temps[h] is None:
                            if h < 6:
                                outside_temps[h] = t_min + (h / 6.0) * (day_info["temp"]["morn"] - t_min if "morn" in day_info["temp"] else 0)
                            elif 6 <= h <= 15:
                                # croissance linéaire de t_min à t_max
                                outside_temps[h] = t_min + (t_max - t_min) * ((h-6) / (15-6))
                            else:
                                # décroissance linéaire de t_max vers t_min (nuit)
                                outside_temps[h] = t_max - (t_max - t_min) * ((h-15) / (24-15))
        else:
            # Pas de données horaires, on utilise les min/max de la première journée pour estimer la courbe
            t_min = 20.0
            t_max = 30.0
            if previsions_jours:
                try:
                    t_min = float(previsions_jours[0]["Min (°C)"])
                    t_max = float(previsions_jours[0]["Max (°C)"])
                except:
                    pass
            for h in range(heures_totales):
                if h < 6:
                    outside_temps[h] = t_min
                elif 6 <= h <= 15:
                    outside_temps[h] = t_min + (t_max - t_min) * ((h-6) / (15-6))
                else:
                    outside_temps[h] = t_max - (t_max - t_min) * ((h-15) / (24-15))

        # Listes de consommation horaire pour chaque scénario
        consommation_horaire_normale = [0.0] * heures_totales
        consommation_horaire_optimisee = [0.0] * heures_totales

        for h in range(heures_totales):
            if start_hour <= h <= end_hour:
                # Scénario normal : climatiseur allumé en continu pendant l'occupation (pleine puissance)
                consommation_horaire_normale[h] = consommation_kw
                # Scénario optimisé : régulation intelligente
                # Calcul de la différence de température entre l'extérieur et la température de confort
                temp_ext = outside_temps[h] if outside_temps[h] is not None else temp_confort
                diff = max(0.0, temp_ext - temp_confort)
                # Ajustement en fonction de l'isolation
                if isolation == "Bonne":
                    diff *= 0.8
                elif isolation == "Faible":
                    diff *= 1.2
                # Ajustement si fenêtres exposées au soleil (on considère un impact surtout aux heures chaudes)
                if fenetres_soleil_bool and 10 <= h <= 16:
                    diff *= 1.1
                # Ajustement en fonction du nombre de personnes (chaleur interne)
                diff *= (1 + 0.05 * (personnes - 1))
                # Calcul du facteur de fonctionnement de la clim (0 à 1)
                # On suppose qu'à +10°C d'écart ou plus, la clim tourne à 100% de sa capacité
                facteur_utilisation = diff / 10.0
                if facteur_utilisation > 1:
                    facteur_utilisation = 1.0
                if facteur_utilisation < 0:
                    facteur_utilisation = 0.0
                # Prise en compte de la technologie inverter (meilleure efficacité à charge partielle)
                if est_inverter:
                    facteur_utilisation *= 0.95  # léger gain d'efficacité
                else:
                    facteur_utilisation *= 1.05  # un non-inverter peut consommer un peu plus pour la même tâche
                if facteur_utilisation > 1:
                    facteur_utilisation = 1.0
                # Consommation optimisée à cette heure (kW * fraction du temps)
                consommation_horaire_optimisee[h] = consommation_kw * facteur_utilisation
            else:
                # En dehors des heures d'occupation, le climatiseur est éteint dans les deux scénarios
                consommation_horaire_normale[h] = 0.0
                consommation_horaire_optimisee[h] = 0.0

        # Calcul des consommations totales quotidiennes (kWh par jour)
        total_kwh_normal = sum(consommation_horaire_normale)
        total_kwh_optimise = sum(consommation_horaire_optimisee)
        # Calcul des coûts quotidiens correspondants
        cout_normal = total_kwh_normal * TARIF_ELECTRICITE
        cout_optimise = total_kwh_optimise * TARIF_ELECTRICITE

        # Affichage des résultats numériques
        st.subheader("Résultats de la simulation :")
        st.write(f"- **Consommation quotidienne - Scénario normal** : {total_kwh_normal:.1f} kWh (coût ≈ {cout_normal:.0f} DZD par jour)")
        st.write(f"- **Consommation quotidienne - Scénario optimisé** : {total_kwh_optimise:.1f} kWh (coût ≈ {cout_optimise:.0f} DZD par jour)")
        # Comparaison et économies
        economie_kwh = total_kwh_normal - total_kwh_optimise
        economie_pourcent = (economie_kwh / total_kwh_normal * 100) if total_kwh_normal > 0 else 0.0
        economie_cout = cout_normal - cout_optimise
        st.write(f"- **Économies potentielles réalisées** : {economie_kwh:.1f} kWh par jour, soit **{economie_pourcent:.0f}%** de moins, ce qui représente environ {economie_cout:.0f} DZD économisés par jour.")

        # Graphique horaire de la consommation pour les deux scénarios
        st.subheader("Profil horaire de consommation électrique")
        import pandas as pd
        heures = list(range(24))
        df_conso = pd.DataFrame({
            "Heure": heures,
            "Consommation normale (kW)": consommation_horaire_normale,
            "Consommation optimisée (kW)": consommation_horaire_optimisee
        })
        df_conso = df_conso.set_index("Heure")
        st.line_chart(df_conso)

        # Section 4: Rapport automatique par IA DeepSeek
        st.header("4. Rapport d'analyse par IA")
        if DEEPSEEK_API_KEY:
            try:
                # Préparation de la requête à l'IA DeepSeek pour le rapport
                rapport_prompt = (
                    "Vous êtes un expert en efficacité énergétique. "
                    "Analysez les résultats de simulation suivants pour un climatiseur domestique :\n"
                    f"- Modèle : {st.session_state.get('ac_modele', 'N/A')}\n"
                    f"- Inverter : {'oui' if est_inverter else 'non'}\n"
                    f"- Puissance frigorifique : {puissance_frigo_kw} kW\n"
                    f"- Consommation électrique : {consommation_kw} kW\n"
                    f"- Ville : {ville_choisie}\n"
                    f"- Isolation : {isolation}\n"
                    f"- Fenêtres ensoleillées : {'oui' if fenetres_soleil_bool else 'non'}\n"
                    f"- Personnes dans la pièce : {personnes}\n"
                    f"- Température de confort : {temp_confort} °C\n"
                    f"- Heures d'utilisation par jour : {X} h\n"
                    f"- Consommation journalière scénario normal : {total_kwh_normal:.1f} kWh (coût {cout_normal:.0f} DZD)\n"
                    f"- Consommation journalière scénario optimisé : {total_kwh_optimise:.1f} kWh (coût {cout_optimise:.0f} DZD)\n"
                    f"- Économie réalisée : {economie_kwh:.1f} kWh/jour ({economie_pourcent:.0f}% de réduction, {economie_cout:.0f} DZD économisés)\n\n"
                    "Rédigez un bref rapport commentant ces résultats, en soulignant les économies d'énergie possibles et la pertinence des choix d'utilisation (isolation, horaires, technologie inverter, etc.)."
                )
                rapport_response = openai.ChatCompletion.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": rapport_prompt}],
                    temperature=0.2,
                    max_tokens=512
                )
                rapport_texte = rapport_response["choices"][0]["message"]["content"]
                st.write(rapport_texte)
            except Exception as e:
                st.error("Erreur lors de la génération du rapport IA DeepSeek.")
        else:
            st.info("Veuillez configurer la clé API DeepSeek pour générer le rapport d'analyse automatique.")

