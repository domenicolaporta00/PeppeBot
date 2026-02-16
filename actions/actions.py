# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker  # type: ignore
from rasa_sdk.executor import CollectingDispatcher  # type: ignore
from rasa_sdk.events import SlotSet  # type: ignore
from rasa_sdk.events import FollowupAction  # type: ignore
import pandas as pd  # type: ignore
from fuzzywuzzy import process  # type: ignore

# Carichiamo il dataset una volta sola all'avvio
try:
    DATASET = pd.read_csv('dataset/dataset_svuotafrigo_finale.csv')
    DATASET['name'] = DATASET['name'].astype(str)
    
    # Pulizia numeri
    DATASET['rating_medio'] = pd.to_numeric(DATASET['rating_medio'], errors='coerce').fillna(0)
    if 'num_voti' in DATASET.columns:
        DATASET['num_voti'] = pd.to_numeric(DATASET['num_voti'], errors='coerce').fillna(0)
    else:
        DATASET['num_voti'] = 0
    
    # IMPORTANTE: Resettiamo l'indice per essere sicuri che sia 0, 1, 2, 3...
    # Questo indice sarà il nostro "ID" univoco.
    DATASET = DATASET.reset_index(drop=True)
    
    print("✅ Dataset caricato. Usa l'indice di riga come ID univoco.")
except Exception as e:
    print(f"❌ ERRORE CARICAMENTO DATASET: {e}")
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

        # 1. Ordina per rating (alto) e numero voti (alto)
        top_recipes = DATASET.sort_values(
            by=['rating_medio', 'num_voti'], 
            ascending=[False, False]
        ).head(5)

        # 2. Costruisce il messaggio di risposta
        message = "⭐ **Here are the Top 5 Recipes from GreenMarket:**\n\n"
        
        for index, row in top_recipes.iterrows():
            name = row['name'].title() # Mette le maiuscole carine
            rating = row['rating_medio']
            votes = int(row['num_voti'])
            minutes = int(row['minutes'])
            
            # Aggiunge una riga per ogni ricetta
            message += f"🏆 **{name}**\n"
            message += f"   Rating: {rating}/5 ({votes} votes) | ⏱️ {minutes} min\n\n"

        # 3. Invia il messaggio all'utente
        dispatcher.utter_message(text=message)

        return []

class ActionSearchByName(Action):
    def name(self) -> Text:
        return "action_search_by_name"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        recipe_name = tracker.get_slot("recipe_name")
        fuzzy_threshold = 60

        if not recipe_name:
            dispatcher.utter_message(text="❓ I didn't catch the name. What do you want to cook?")
            return [SlotSet('recipe_name', None)]

        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        # 1. Ricerca "Larga" (Partial Match) - Come volevi tu
        # Se cerco "Bread", trova "Banana Bread", "Bread", "Garlic Bread".
        matches = DATASET[DATASET['name'].str.contains(recipe_name, case=False, na=False, regex=False)]

        # 2. Fuzzy se vuoto
        if matches.empty:
            try:
                all_recipes = [str(x) for x in DATASET['name'].tolist()]
                best_match, score = process.extractOne(recipe_name, all_recipes)
                if score >= fuzzy_threshold:
                    matches = DATASET[DATASET['name'].str.contains(best_match, case=False, na=False, regex=False)]
            except Exception:
                pass

        # 3. GESTIONE RISULTATI
        if not matches.empty:
            # Ordiniamo per qualità
            matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
            
            # --- ORA MOSTRIAMO SEMPRE I BOTTONI SE C'È AMBIGUITÀ ---
            # Anche se i nomi sono uguali (es. due ricette "Bread"), avendo ID diversi
            # li tratteremo come distinti.
            
            count = len(matches)
            top_matches = matches.head(5) # Prendiamo le prime 5

            # Se c'è SOLA 1 ricetta, mostriamo direttamente i dettagli (per comodità)
            if count == 1:
                # Chiamiamo l'altra action "manualmente" passandogli l'ID
                unique_id = top_matches.index[0] # L'indice originale del DataFrame
                return [SlotSet("recipe_id", str(unique_id)), FollowupAction("action_select_recipe_by_id")]
            
            # Se ce n'è più di una (es. Bread, Banana Bread), mostriamo i bottoni
            else:
                dispatcher.utter_message(text=f"🔍 I found {count} recipes containing **'{recipe_name}'**. Please select one:")
                
                buttons = []
                for index, row in top_matches.iterrows():
                    r_name = row['name'].title()
                    r_rate = row['rating_medio']
                    
                    # Titolo del bottone: "Banana Bread (4.5⭐)"
                    title = f"{r_name} ({r_rate}⭐)"
                    
                    # PAYLOAD MAGICO: Passiamo l'ID (index), NON il nome!
                    # Esempio: /select_recipe{"recipe_id": "452"}
                    payload = f'/select_recipe{{"recipe_id":"{index}"}}'
                    
                    buttons.append({"title": title, "payload": payload})
                
                dispatcher.utter_message(buttons=buttons)
                return []
        
        else:
            dispatcher.utter_message(text=f"😔 I'm sorry, I couldn't find anything matching **{recipe_name}**.")
            return [SlotSet('recipe_name', None)]


# --- AZIONE 2: MOSTRA DETTAGLI DA ID (Blindata) ---
class ActionSelectRecipeById(Action):
    def name(self) -> Text:
        return "action_select_recipe_by_id"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        
        # Recupera l'ID dal click del bottone
        recipe_id = tracker.get_slot("recipe_id")
        
        if recipe_id is None or DATASET is None:
            dispatcher.utter_message(text="⚠️ Error: Recipe selection lost.")
            return []

        try:
            # Convertiamo l'ID in intero per cercare nel DataFrame
            r_id = int(recipe_id)
            
            # Cerchiamo la riga esatta usando l'indice (iloc non va bene se l'indice non è posizionale, 
            # ma qui usiamo .loc perché l'indice è l'ID del dataset originale)
            if r_id in DATASET.index:
                row = DATASET.loc[r_id]
                
                r_name = row['name'].title()
                r_time = row['minutes']
                r_rate = row['rating_medio']
                r_votes = int(row['num_voti'])
                
                r_tags = str(row['tags']).replace('[','').replace(']','').replace("'", "").replace('"', "")
                r_ingr = str(row['ingredients']).replace('[','').replace(']','').replace("'", "").replace('"', "")
                r_steps = str(row['steps']).replace('[','').replace(']','').replace("'", "").replace('"', "")

                message = (
                    f"🍽️ **{r_name}**\n"
                    f"⭐ Rating: {r_rate}/5 ({r_votes} votes)\n"
                    f"⏱️ Cooking Time: {r_time} min\n"
                    f"🏷️ Tags: {r_tags}\n\n"
                    f"🥦 **Ingredients:**\n{r_ingr}\n\n"
                    f"👨‍🍳 **Steps:**\n{r_steps}"
                )
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="⚠️ Recipe ID not found in database.")
                
        except ValueError:
            dispatcher.utter_message(text="⚠️ Invalid Recipe ID.")

        # Puliamo lo slot ID
        return [SlotSet("recipe_id", None)]
