import streamlit as st
import requests

# API Keys
DEEPSEEK_API_KEY = "sk-c2463319fd4d461d9172e8b5b49936dd"
OPENWEATHERMAP_API_KEY = "420227af9037639d0d68ac9deafead1a"

# Functions to fetch data
def fetch_climatiseur_data(marque):
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        json={"model": "deepseek-chat", "messages": [{"role": "user", "content": f"Donne la consommation électrique moyenne en W pour le climatiseur {marque}"}]},
        headers=headers
    )
    result = response.json()
    return result["choices"][0]["message"]["content"]

def get_temperature(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHERMAP_API_KEY}&units=metric"
    response = requests.get(url).json()
    return response['main']['temp']

# Streamlit interface
st.title('Optimisation Énergétique Climatiseur Domestique')

marque = st.text_input("Marque/Modèle du climatiseur")
city = st.text_input("Ville")
surface = st.number_input("Surface de la pièce (m²)", min_value=5, max_value=500, value=20)
isolation = st.selectbox("Type d'isolation", ["Faible", "Moyenne", "Bonne"])
fenetres = st.selectbox("Présence de fenêtres", ["Oui", "Non"])
prix_elec = st.number_input("Prix d'électricité (DA/kWh)", min_value=1.0, max_value=50.0, value=5.0)
confort_temp = st.slider("Température de confort (°C)", 18, 30, 24)

if st.button("Calculer l'Optimisation"):
    with st.spinner('Recherche données du climatiseur...'):
        clim_conso = fetch_climatiseur_data(marque)

    with st.spinner('Recherche température extérieure...'):
        temp_ext = get_temperature(city)

    # Estimation basique pour la démonstration
    facteur_isolation = {"Faible": 1.5, "Moyenne": 1.2, "Bonne": 1.0}[isolation]
    facteur_fenetre = 1.2 if fenetres == "Oui" else 1.0

    conso_base_watt = float(''.join(filter(str.isdigit, clim_conso)))

    conso_reelle = conso_base_watt * facteur_isolation * facteur_fenetre * (1 + abs(temp_ext - confort_temp) / 10)

    conso_jour = (conso_reelle / 1000) * 8  # utilisation moyenne 8h/jour
    cout_jour = conso_jour * prix_elec

    st.subheader("Résultat de la Simulation")
    st.write(f"**Température extérieure actuelle :** {temp_ext} °C")
    st.write(f"**Consommation réelle estimée :** {conso_reelle:.2f} W")
    st.write(f"**Coût journalier estimé :** {cout_jour:.2f} DA")

    st.subheader("Suggestions d'Optimisation")

    if isolation == "Faible":
        gain_iso = cout_jour * 0.25
        st.write(f"Améliorer l'isolation peut vous faire économiser jusqu'à {gain_iso:.2f} DA/jour.")

    if fenetres == "Oui":
        gain_fenetre = cout_jour * 0.1
        st.write(f"Limiter les pertes thermiques des fenêtres peut économiser environ {gain_fenetre:.2f} DA/jour.")

    ajust_temp_gain = cout_jour * 0.05 * abs(confort_temp - 24)
    if ajust_temp_gain > 0:
        st.write(f"Rapprocher votre température de confort vers 24°C pourrait économiser environ {ajust_temp_gain:.2f} DA/jour.")
