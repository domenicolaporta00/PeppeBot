# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import pandas as pd

# Carichiamo il dataset UNA VOLTA sola all'avvio per velocità
# Assicurati che il file sia nella cartella principale del progetto
try:
    DATASET = pd.read_csv('dataset/dataset_svuotafrigo_finale.csv')
    print("✅ Dataset caricato correttamente in actions.py")
except FileNotFoundError:
    print("❌ ERRORE: dataset_svuotafrigo.csv non trovato nella cartella principale!")
    DATASET = None

class ActionShowTopRated(Action):

    def name(self) -> Text:
        return "action_show_top_rated"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        if DATASET is None:
            dispatcher.utter_message(text="I'm sorry, I can't access the recipe database right now. 😔")
            return []

        # 1. Ordiniamo per rating (alto) e numero voti (alto)
        #    Così evitiamo ricette con 5 stelle ma 1 solo voto.
        top_recipes = DATASET.sort_values(
            by=['rating_medio', 'num_voti'], 
            ascending=[False, False]
        ).head(5)

        # 2. Costruiamo il messaggio di risposta
        message = "⭐ **Here are the Top 5 Recipes from GreenMarket:**\n\n"
        
        for index, row in top_recipes.iterrows():
            name = row['name'].title() # Mette le maiuscole carine
            rating = row['rating_medio']
            votes = int(row['num_voti'])
            minutes = int(row['minutes'])
            
            # Aggiungiamo una riga per ogni ricetta
            message += f"🏆 **{name}**\n"
            message += f"   Rating: {rating}/5 ({votes} votes) | ⏱️ {minutes} min\n\n"

        # 3. Inviamo il messaggio all'utente
        dispatcher.utter_message(text=message)

        return []
