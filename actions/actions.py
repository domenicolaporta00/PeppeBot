# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


import ast
import re
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker  # type: ignore
from rasa_sdk.executor import CollectingDispatcher  # type: ignore
from rasa_sdk.events import SlotSet  # type: ignore
from rasa_sdk.events import FollowupAction  # type: ignore
from rasa_sdk.forms import FormValidationAction  # type: ignore
from rasa_sdk.types import DomainDict  # type: ignore
import pandas as pd  # type: ignore
from fuzzywuzzy import process, fuzz  # type: ignore

PERCORSO_DATASET = 'dataset/dataset_svuotafrigo_finale.csv'
ALL_UNIQUE_TAGS = []
ALL_UNIQUE_INGREDIENTS = []
DATASET = None

# Caricamento del dataset
try:
    print(f"📂 Caricamento dataset da: {PERCORSO_DATASET}")
    DATASET = pd.read_csv(PERCORSO_DATASET)
    DATASET['name'] = DATASET['name'].astype(str)
    
    # Pulizia numeri e reset indici per gli ID
    DATASET['rating_medio'] = pd.to_numeric(DATASET['rating_medio'], errors='coerce').fillna(0)
    if 'num_voti' in DATASET.columns:
        DATASET['num_voti'] = pd.to_numeric(DATASET['num_voti'], errors='coerce').fillna(0)
    else:
        DATASET['num_voti'] = 0
    
    DATASET = DATASET.reset_index(drop=True) # FONDAMENTALE PER GLI ID

    # --- 1. INDICIZZAZIONE TAG ---
    print("🔄 Indicizzazione dei TAG...")
    all_tags_set = set()
    for tag_str in DATASET['tags'].dropna():
        try:
            t_list = ast.literal_eval(tag_str)
            for t in t_list:
                all_tags_set.add(t.lower())
        except:
            pass
    ALL_UNIQUE_TAGS = list(all_tags_set)
    print(f"✅ Tag indicizzati: {len(ALL_UNIQUE_TAGS)}")

    # --- 2. INDICIZZAZIONE INGREDIENTI ---
    print("🔄 Indicizzazione degli INGREDIENTI...")
    all_ing_set = set()
    for ing_str in DATASET['ingredients'].dropna():
        try:
            # ing_str è "['onion', 'garlic']"
            i_list = ast.literal_eval(ing_str)
            for i in i_list:
                all_ing_set.add(i.lower().strip())
        except:
            pass
    ALL_UNIQUE_INGREDIENTS = list(all_ing_set)
    print(f"✅ Ingredienti indicizzati: {len(ALL_UNIQUE_INGREDIENTS)}")

except Exception as e:
    print(f"❌ ERRORE CRITICO CARICAMENTO DATASET: {e}")
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
            name = row['name'].title() # Mette le maiuscole a tutte le parole
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

        # 1. Ricerca tutte le ricette che contengono recipe_name
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
            # Ordina per qualità
            matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
            
            count = len(matches)
            top_matches = matches.head(5) # Prendiamo le prime 5

            # Se c'è SOLA 1 ricetta, mostra direttamente i dettagli
            if count == 1:
                # Chiama l'altra action "manualmente" passandogli l'ID
                unique_id = top_matches.index[0] # L'indice originale del DataFrame
                return [SlotSet("recipe_id", str(unique_id)), FollowupAction("action_select_recipe_by_id")]
            
            # Se ce n'è più di una (es. Bread, Banana Bread), mostra i bottoni
            else:
                testo_risposta = f"🔍 I found {count} recipes containing **'{recipe_name}'**. Here are the top {len(top_matches)}:"
                
                buttons = []
                for index, row in top_matches.iterrows():
                    r_name = row['name'].title()
                    r_rate = row['rating_medio']
                    
                    # Aggiungiamo un'icona per allungare leggermente il testo e forzare Telegram a metterli in colonna
                    title = f"👨‍🍳 {r_name} ({r_rate}⭐)"
                    payload = f'/select_recipe{{"recipe_id":"{index}"}}'
                    
                    buttons.append({"title": title, "payload": payload})
                
                # Usiamo il metodo nativo di Rasa: è l'unico blindato al 100%
                dispatcher.utter_message(text=testo_risposta, buttons=buttons)
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
            r_id = int(recipe_id)
            
            if r_id in DATASET.index:
                # Estrae la riga dall'ID
                row = DATASET.loc[r_id]
                
                # Formatta il messaggio
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

        # Pulisce lo slot ID
        return [SlotSet("recipe_id", None)]
    
class ActionSearchByCategory(Action):
    def name(self) -> Text:
        return "action_search_by_category"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_input = tracker.get_slot("category")
        
        if not user_input:
            dispatcher.utter_message(text="❓ What category are you looking for? (e.g., Winter, Spicy, Vegan)")
            return []

        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        # Controlla che sia una lista
        if isinstance(user_input, str):
            user_input = [user_input]

        print(f"🔍 Categorie cercate dall'utente (raw): {user_input}")

        # Iniziamo col dataset completo
        matches = DATASET.copy()
        
        # Lista per tenere traccia dei tag validi trovati (per il messaggio finale)
        found_tags = []

        # --- CICLO DI FILTRAGGIO ---
        # Per ogni tag chiesto dall'utente, restringe i risultati
        for item in user_input:
            search_tag = item.lower().strip()
            
            # 1. Fuzzy Check per il singolo tag
            current_tag_matches = matches[matches['tags'].str.contains(search_tag, case=False, na=False, regex=False)]
            
            # Se il tag non è contenuto nel DB, prova a correggerlo usando ALL_UNIQUE_TAGS
            if current_tag_matches.empty and ALL_UNIQUE_TAGS:
                try:
                    best_match, score = process.extractOne(search_tag, ALL_UNIQUE_TAGS)
                    if score >= 65:
                        print(f"💡 Fuzzy Correction: '{search_tag}' -> '{best_match}'")
                        search_tag = best_match
                except:
                    pass
            
            # Aggiunge il tag (originale o corretto) alla lista dei confermati
            found_tags.append(search_tag)

            # 2. APPLICAZIONE FILTRO
            # Restringiamo il dataset `matches` solo alle righe che hanno QUESTO tag
            matches = matches[matches['tags'].str.contains(search_tag, case=False, na=False, regex=False)]
            
            # Se a un certo punto non rimane nulla (es. "Vegan" + "Steak"), stop
            if matches.empty:
                break

        # --- RISULTATI ---
        tags_str = " + ".join([f"**{t}**" for t in found_tags])
        
        # Se trova qualcosa, mostra i top 5 risultati ordinati per rating
        if not matches.empty:
            matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
            count = len(matches)
            top_matches = matches.head(5)

            # Salviamo il testo in una variabile invece di inviarlo da solo
            testo_risposta = f"🔍 I found {count} recipes matching {tags_str}! Here are the best ones:"
            
            buttons = []
            for index, row in top_matches.iterrows():
                r_name = row['name'].title()
                r_rate = row['rating_medio']
                
                # Aggiungiamo l'icona del cuoco per allungare il testo del bottone (layout verticale Telegram)
                title = f"👨‍🍳 {r_name} ({r_rate}⭐)"
                payload = f'/select_recipe{{"recipe_id":"{index}"}}'
                buttons.append({"title": title, "payload": payload})
            
            # Invia testo e bottoni in un unico pacchetto
            dispatcher.utter_message(text=testo_risposta, buttons=buttons)
        
        else:
            dispatcher.utter_message(text=f"😔 No recipes found matching ALL these criteria: {tags_str}. Try searching for just one of them.")
        
        # Resetta lo slot
        return [SlotSet("category", None)]
    
class ActionAskNutrition(Action):
    def name(self) -> Text:
        return "action_ask_nutrition"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Prende tutti gli slot possibili
        recipe_id = tracker.get_slot("recipe_id")
        recipe_name = tracker.get_slot("recipe_name")
        requested_nutrient = tracker.get_slot("nutrient")
        
        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        row = None

        # --- 1. PRIORITÀ ASSOLUTA ALL'ID (Click dal Bottone) ---
        if recipe_id:
            try:
                r_index = int(recipe_id)
                # Controlliamo se l'indice è valido
                if 0 <= r_index < len(DATASET):
                    # Recupera la riga dall'ID usando .loc (o .iloc se usi indici posizionali, ma .loc è più sicuro per gli ID)
                    row = DATASET.loc[r_index]
                    print(f"✅ Trovata ricetta via ID: {r_index} -> {row['name']}")
                else:
                    dispatcher.utter_message(text="⚠️ Invalid Recipe ID.")
                    return [SlotSet("recipe_id", None)]
            except ValueError:
                pass
            except KeyError:
                dispatcher.utter_message(text="⚠️ Invalid Recipe ID.")
                return [SlotSet("recipe_id", None)]

        # --- 2. RICERCA PER NOME ---
        if row is None and recipe_name:
            search_term = recipe_name.lower().strip()
            
            # Ricerca ampia
            matches = DATASET[DATASET['name'].str.contains(search_term, case=False, na=False, regex=False)]
            
            # Fuzzy fallback
            if matches.empty:
                try:
                    all_names = DATASET['name'].tolist()
                    best_match, score = process.extractOne(search_term, all_names)
                    if score >= 60:
                        dispatcher.utter_message(text=f"Did you mean **{best_match}**? Checking... 🕵️")
                        matches = DATASET[DATASET['name'].str.contains(best_match, case=False, na=False, regex=False)]
                except:
                    pass

            if not matches.empty:
                matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
                unique_names = matches['name'].unique()
                
                # Se ci sono ambiguità (es. "Bread" vs "Banana Bread"), mostra i bottoni
                if len(unique_names) > 1:
                    testo_risposta = f"🔍 I found multiple recipes for **'{recipe_name}'**. Select the exact one to see its nutritional info:"
                    
                    buttons = []
                    # Prendiamo i primi 5 risultati diversi
                    for index, r in matches.head(5).iterrows():
                        r_name = r['name'].title()
                        
                        # Passiamo SOLO l'ID. Rasa si ricorderà da solo il nutriente dalla memoria!
                        payload = f'/ask_nutrition{{"recipe_id":"{index}"}}'
                        
                        buttons.append({"title": f"🥗 {r_name}", "payload": payload})
                    
                    # Invia il messaggio combinato (Telegram safe)
                    dispatcher.utter_message(text=testo_risposta, buttons=buttons)
                    return []
                
                else:
                    # Match unico
                    row = matches.iloc[0]
            else:
                dispatcher.utter_message(text=f"😔 I couldn't find nutritional info for **{recipe_name}**.")
                return [SlotSet("recipe_name", None)]

        # --- 3. MOSTRA RISULTATI (Se esiste 'row') ---
        if row is not None:
            r_name = row['name'].title()
            
            # MAPPING COLONNE
            column_map = {
                "calories": "calories", "total_fat": "total_fat", "fat": "total_fat",
                "sugar": "sugar", "sodium": "sodium", "protein": "protein",
                "saturated_fat": "saturated_fat", "saturated": "saturated_fat",
                "carbohydrates": "carbohydrates", "carbs": "carbohydrates"
            }

            # Se l'utente ha chiesto un nutriente specifico...
            if requested_nutrient:
                clean_nutrient = requested_nutrient.lower().replace(" ", "_")
                col_name = column_map.get(clean_nutrient, clean_nutrient)

                # Se il nutriente esiste...
                if col_name in row:
                    value = row[col_name]
                    unit = "kcal" if col_name == "calories" else "% PDV"
                    dispatcher.utter_message(text=f"📊 **{r_name}** contains **{value} {unit}** of {requested_nutrient}.")
                else:
                    dispatcher.utter_message(text=f"⚠️ Info about '{requested_nutrient}' not available.")
            # Altrimenti mostra tutto
            else:
                msg = (
                    f"📊 **Nutritional Info for {r_name}**:\n\n"
                    f"🔥 **Calories:** {row['calories']} kcal\n"
                    f"🥓 **Total Fat:** {row['total_fat']}% PDV\n"
                    f"🍬 **Sugar:** {row['sugar']}% PDV\n"
                    f"🧂 **Sodium:** {row['sodium']}% PDV\n"
                    f"🥩 **Protein:** {row['protein']}% PDV\n"
                    f"🧈 **Saturated Fat:** {row['saturated_fat']}% PDV\n"
                    f"🍞 **Carbohydrates:** {row['carbohydrates']}% PDV\n\n"
                    f"*(PDV = Percent Daily Value)*"
                )
                dispatcher.utter_message(text=msg)

        # Resetta tutti gli slot
        return [SlotSet("recipe_name", None), SlotSet("recipe_id", None), SlotSet("nutrient", None)]
    
class ActionAskCookingTime(Action):
    def name(self) -> Text:
        return "action_ask_cooking_time"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Prende tutti gli slot possibili (id se viene da bottone, altrimenti nome per ricerca)
        recipe_id = tracker.get_slot("recipe_id")
        recipe_name = tracker.get_slot("recipe_name")
        
        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        row = None

        # --- 1. PRIORITÀ ID ---
        if recipe_id:
            try:
                r_index = int(recipe_id)
                if 0 <= r_index < len(DATASET):
                    # Usiamo .loc perché r_index è l'ID reale (l'indice del dataframe)
                    row = DATASET.loc[r_index]
                else:
                    dispatcher.utter_message(text="⚠️ Invalid Recipe ID.")
                    return [SlotSet("recipe_id", None)]
            except ValueError:
                pass
            except KeyError:
                dispatcher.utter_message(text="⚠️ Invalid Recipe ID.")
                return [SlotSet("recipe_id", None)]

        # --- 2. RICERCA PER NOME ---
        if row is None and recipe_name:
            search_term = recipe_name.lower().strip()
            
            # Ricerca ampia
            matches = DATASET[DATASET['name'].str.contains(search_term, case=False, na=False, regex=False)]
            
            # Fuzzy fallback
            if matches.empty:
                try:
                    all_names = DATASET['name'].tolist()
                    best_match, score = process.extractOne(search_term, all_names)
                    if score >= 60:
                        dispatcher.utter_message(text=f"Did you mean **{best_match}**? Checking time... ⏱️")
                        matches = DATASET[DATASET['name'].str.contains(best_match, case=False, na=False, regex=False)]
                except:
                    pass

            if not matches.empty:
                matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
                unique_names = matches['name'].unique()
                
                # AMBIGUITÀ -> BOTTONI CON ID
                if len(unique_names) > 1:
                    # Salviamo il testo in una variabile
                    testo_risposta = f"⏱️ I found multiple recipes for **'{recipe_name}'**. Which one?"
                    
                    buttons = []
                    for index, r in matches.head(5).iterrows():
                        r_name = r['name'].title()
                        # Payload punta a questa azione ma con l'ID
                        payload = f'/ask_cooking_time{{"recipe_id":"{index}"}}'
                        
                        # Aggiungiamo un'icona per favorire il layout verticale su Telegram
                        buttons.append({"title": f"⏳ {r_name}", "payload": payload})
                    
                    # Inviamo il pacchetto completo testo + bottoni
                    dispatcher.utter_message(text=testo_risposta, buttons=buttons)
                    return []
                
                else:
                    # Match unico
                    row = matches.iloc[0]
            else:
                dispatcher.utter_message(text=f"😔 I couldn't find cooking times for **{recipe_name}**.")
                return [SlotSet("recipe_name", None)]

        # --- 3. MOSTRA RISULTATO ---
        if row is not None:
            r_name = row['name'].title()
            r_minutes = row['minutes']
            
            # Formattazione della risposta
            if r_minutes > 60:
                hours = int(r_minutes // 60)
                mins = int(r_minutes % 60)
                time_str = f"{hours}h {mins}m"
            else:
                time_str = f"{r_minutes} minutes"

            dispatcher.utter_message(text=f"⏱️ **{r_name}** takes about **{time_str}** to make.")

        # Reset slot
        return [SlotSet("recipe_name", None), SlotSet("recipe_id", None)]

class ActionSearchByIngredient(Action):
    def name(self) -> Text:
        return "action_search_by_ingredient"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # 1. Recupera Input Utente (slot 'ingredient')
        user_input = tracker.get_slot("ingredient")
        
        if not user_input:
            dispatcher.utter_message(text="❓ What ingredients do you have? (e.g., Chicken, Onion, Eggs)")
            return []

        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        # Controlla che sia una lista
        if isinstance(user_input, str):
            user_input = [user_input]

        print(f"🥦 Ingredienti cercati dall'utente (raw): {user_input}")

        matches = DATASET.copy()
        
        # Lista per tenere traccia degli ingredienti validi trovati
        found_ingredients = []

        # --- CICLO DI FILTRAGGIO ---
        for item in user_input:
            search_item = item.lower().strip()
                        
            # Controllo rapido se c'è già un match esatto nel subset corrente
            current_matches = matches[matches['ingredients'].str.contains(search_item, case=False, na=False, regex=False)]
            
            # Fuzzy fallback
            if current_matches.empty and ALL_UNIQUE_INGREDIENTS:
                try:
                    best_match, score = process.extractOne(search_item, ALL_UNIQUE_INGREDIENTS)
                    if score >= 70:
                        print(f"💡 Fuzzy Ingredient Correction: '{search_item}' -> '{best_match}'")
                        search_item = best_match
                except:
                    pass
            
            # Aggiunge l'ingrediente (originale o corretto)
            found_ingredients.append(search_item)

            # Restringe il dataset `matches` alle sole righe che contengono questo ingrediente
            matches = matches[matches['ingredients'].str.contains(search_item, case=False, na=False, regex=False)]
            
            # Se a un certo punto non rimane nulla, stop
            if matches.empty:
                break

        # --- RISULTATI ---
        ing_str = " + ".join([f"**{i}**" for i in found_ingredients])
        
        # Se ha trovato qualcosa, mostra i top 5 risultati ordinati per rating
        if not matches.empty:
            matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
            count = len(matches)
            top_matches = matches.head(5)

            # Salviamo il testo in una variabile
            testo_risposta = f"🍳 I found {count} recipes using {ing_str}! Here are the best ones:"
            
            buttons = []
            for index, row in top_matches.iterrows():
                r_name = row['name'].title()
                r_rate = row['rating_medio']
                
                # Aggiungiamo l'icona per allungare il testo e forzare il layout verticale su Telegram
                title = f"🍳 {r_name} ({r_rate}⭐)"
                payload = f'/select_recipe{{"recipe_id":"{index}"}}'
                buttons.append({"title": title, "payload": payload})
            
            # Invia testo e bottoni insieme!
            dispatcher.utter_message(text=testo_risposta, buttons=buttons)
            
        # Altrimenti, se non trova nulla, mostra un messaggio di errore
        else:
            dispatcher.utter_message(text=f"😔 No recipes found containing ALL these ingredients: {ing_str}. Try searching for just one of them.")
        
        # Resetta lo slot
        return [SlotSet("ingredient", None)]
    
class ValidateSvuotaFrigoForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_svuota_frigo_form"

    # ==========================================
    # 1. VALIDAZIONE INGREDIENTI
    # ==========================================
    def validate_ingredient(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:

        # Controllo se l'utente vuole fermarsi
        intent = tracker.latest_message.get("intent", {}).get("name")
        text = tracker.latest_message.get("text", "").lower()
        if intent == "stop" or text.strip() in ["stop", "exit", "cancel", "close"]:
            return {"ingredient": None}
        
        # Estrae gli ingredienti usando le entità
        extracted = [e["value"] for e in tracker.latest_message.get("entities", []) if e["entity"] == "ingredient"]
        
        # Prova a estrarre manualmente dagli slot se le entità non hanno funzionato (es. "I have chicken and onion")
        if not extracted:
            text = tracker.latest_message.get("text", "").lower()
            for word in ["i have ", "use ", "some ", "only ", "want "]:
                text = text.replace(word, "")
            extracted = [i.strip() for i in text.replace(" and ", ",").split(",") if len(i.strip()) > 1]

        # Resetta tutto se non riesce ad estrarre nulla
        if not extracted:
            dispatcher.utter_message(text="🛑 I didn't catch anything! Please tell me the INGREDIENTS you want to use.")
            return {"ingredient": None, "time_limit": None, "category": None}

        valid_ingredients = []
        # Controlla ogni ingrediente estratto: se è esatto, ok; altrimenti prova a correggerlo con fuzzy matching
        for item in extracted:
            item_clean = item.lower()
            if item_clean in ALL_UNIQUE_INGREDIENTS:
                valid_ingredients.append(item_clean)
            else:
                if ALL_UNIQUE_INGREDIENTS:
                    best_match, score = process.extractOne(item_clean, ALL_UNIQUE_INGREDIENTS, scorer=fuzz.ratio)
                    if score >= 80:
                        print(f"✅ Validated Ing: '{item_clean}' -> '{best_match}'")
                        valid_ingredients.append(best_match)

        # Se dopo tutto questo non abbiamo ingredienti validi, mostra un messaggio di errore e resetta tutto
        if not valid_ingredients:
            dispatcher.utter_message(text="🛑 I don't recognize those as ingredients. Please give me valid food items (e.g., chicken, eggs).")
            return {"ingredient": None, "time_limit": None, "category": None}

        # SUCCESSO: Salva gli ingredienti e azzera il tempo e la categoria per impedire salti!
        return {"ingredient": valid_ingredients, "time_limit": None, "category": None}

    # ==========================================
    # 2. VALIDAZIONE TEMPO
    # ==========================================
    def validate_time_limit(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        # Controllo se l'utente vuole fermarsi
        intent = tracker.latest_message.get("intent", {}).get("name")
        text = tracker.latest_message.get("text", "").lower()
        if intent == "stop" or text.strip() in ["stop", "exit", "cancel", "close"]:
            return {"time_limit": None}
        
        # Estrae i numeri dal testo (utilizzando le espressioni regolari)
        numbers = re.findall(r'\d+', text)
        
        # Se non trova numeri, mostra un messaggio di errore e resetta tempo e categoria
        if not numbers:
            dispatcher.utter_message(text="🛑 I need a number! How many MINUTES do you have?")
            return {"time_limit": None, "category": None}
            
        # SUCCESSO: Salva il tempo e azzeriamo la categoria per evitare salti
        return {"time_limit": int(numbers[0]), "category": None}

    # ==========================================
    # 3. VALIDAZIONE CATEGORIE / TAGS
    # ==========================================
    def validate_category(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        # Controllo se l'utente vuole fermarsi
        intent = tracker.latest_message.get("intent", {}).get("name")
        text = tracker.latest_message.get("text", "").lower()
        if intent == "stop" or text.strip() in ["stop", "exit", "cancel", "close"]:
            return {"category": None}
                
        # Controllo se l'utente vuole saltare questa parte
        if text in ["none", "nothing", "no", "skip", "any", "i don't care"]:
            return {"category": ["none"]}

        # Prova a estrarre le categorie usando le entità
        extracted = [e["value"] for e in tracker.latest_message.get("entities", []) if e["entity"] == "category"]
        print("Extracted categories:", extracted)

        # Se non riesce ad estrarre nulla, prova a fare un parsing manuale
        if not extracted:
            text = tracker.latest_message.get("text", "").lower()
            print("Raw user input for category:", text)
            for word in ["i want ", "give me ", " tag", " food", " recipes", " recipe"]:
                text = text.replace(word, "")
            extracted = [i.strip() for i in text.replace(" and ", ",").split(",") if len(i.strip()) > 1]
            print("Manually extracted categories:", extracted)

        # Se ancora non riesce ad estrarre nulla, mostra un messaggio di errore e resetta la categoria
        if not extracted:
            dispatcher.utter_message(text="🛑 I didn't catch anything. Please provide a tag (like 'Vegan') or type 'none'.")
            return {"category": None}

        valid_tags = []
        # Controlla ogni tag estratto: se è esatto, ok; altrimenti prova a correggerlo con fuzzy matching
        for item in extracted:
            item_clean = item.lower()
            if item_clean in ALL_UNIQUE_TAGS:
                valid_tags.append(item_clean)
            else:
                if ALL_UNIQUE_TAGS:
                    best_match, score = process.extractOne(item_clean, ALL_UNIQUE_TAGS, scorer=fuzz.ratio)
                    if score >= 75:
                        print(f"✅ Validated Tag: '{item_clean}' -> '{best_match}'")
                        valid_tags.append(best_match)

        # Se dopo tutto questo non abbiamo tag validi, mostra un messaggio di errore e resetta la categoria
        if not valid_tags:
            dispatcher.utter_message(text="🛑 I don't recognize those tags. Give me a valid category (like 'Easy', 'Winter') or type 'none'.")
            return {"category": None}

        return {"category": valid_tags}

class ActionSubmitSvuotaFrigo(Action):
    def name(self) -> Text:
        return "action_submit_svuota_frigo"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Recupera i dati (già perfetti e validati dalla Form!)
        ingredients = tracker.get_slot("ingredient")
        time_limit = tracker.get_slot("time_limit")
        categories = tracker.get_slot("category")

        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        matches = DATASET.copy()

        # FILTRO TEMPO (calcolo più veloce)
        if time_limit:
            matches = matches[matches['minutes'] <= int(time_limit)]

        # FILTRO INGREDIENTI (Ricerca Esatta nell'Array)
        if not matches.empty and ingredients:
            def check_ingredients(row_ing_str):
                try:
                    # Converte la stringa "['olive', 'garlic']" in una VERA lista Python
                    recipe_ings = [x.lower().strip() for x in ast.literal_eval(row_ing_str)]
                    
                    # Controlla che TUTTI gli ingredienti cercati siano nella lista
                    for search_item in ingredients:
                        if search_item.lower() not in recipe_ings:
                            return False
                    return True
                except:
                    return False

            # Applica il filtro ingredienti        
            matches = matches[matches['ingredients'].apply(check_ingredients)]

        # 4. FILTRO CATEGORIE / TAGS (Ricerca Esatta nell'Array)
        if not matches.empty and categories and categories != ["none"]:
            def check_tags(row_tag_str):
                try:
                    # Stessa logica degli ingredienti
                    recipe_tags = [x.lower().strip() for x in ast.literal_eval(row_tag_str)]
                    for cat in categories:
                        if cat.lower() not in recipe_tags:
                            return False
                    return True
                except:
                    return False

            # Applica il filtro tags        
            matches = matches[matches['tags'].apply(check_tags)]

        # --- MOSTRA I RISULTATI ---
        ing_display = ", ".join(ingredients) if ingredients else "any ingredients"
        cat_display = "" if not categories or categories == ["none"] else f" and tags ({', '.join(categories)})"
        
        if not matches.empty:
            # Ordina per qualità (rating e numero di voti)
            matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
            count = len(matches)
            top_matches = matches.head(5)

            # Salviamo il testo in una variabile
            testo_risposta = f"🎉 SUCCESS! I found {count} recipes using **{ing_display}**, under **{time_limit} mins**{cat_display}:"
            
            buttons = []
            for index, row in top_matches.iterrows():
                r_name = row['name'].title()
                
                # Aggiungiamo icona per forzare l'incolonnamento su Telegram
                title = f"🍽️ {r_name} ({row['minutes']}m)"
                payload = f'/select_recipe{{"recipe_id":"{index}"}}'
                
                buttons.append({"title": title, "payload": payload})
            
            # Invio combinato di testo e bottoni!
            dispatcher.utter_message(text=testo_risposta, buttons=buttons)
        else:
            dispatcher.utter_message(text=f"😔 I'm sorry, I couldn't find any recipe combining **{ing_display}** under **{time_limit} minutes**{cat_display}. The fridge is too empty!")

        # PULIZIA TOTALE (Svuota gli slot per la prossima ricerca)
        return [SlotSet("ingredient", None), SlotSet("time_limit", None), SlotSet("category", None)]
    
# =============================================================================
# VALIDAZIONE FORM NUTRIZIONALE
# =============================================================================
class ValidateNutritionSearchForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_nutrition_search_form"

    def extract_number(self, text: str):
        numbers = re.findall(r'\d+', text)
        if numbers:
            return int(numbers[0])
        return None

    # 1. Calorie
    def validate_max_calories(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        # Controllo se l'utente vuole fermarsi
        intent = tracker.latest_message.get("intent", {}).get("name")
        text = tracker.latest_message.get("text", "").lower()
        if intent == "stop" or text.strip() in ["stop", "exit", "cancel", "close"]:
            return {"max_calories": None}
        
        num = self.extract_number(tracker.latest_message.get("text", ""))
        if num is None:
            dispatcher.utter_message(text="🛑 I need a number! Please enter the max CALORIES (kcal).")
            # Azzera i successivi
            return {"max_calories": None, "max_carbs": None, "max_fat": None, "max_protein": None}
        return {"max_calories": num, "max_carbs": None, "max_fat": None, "max_protein": None}

    # 2. Carboidrati (stesso discorso delle calorie)
    def validate_max_carbs(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        intent = tracker.latest_message.get("intent", {}).get("name")
        text = tracker.latest_message.get("text", "").lower()
        if intent == "stop" or text.strip() in ["stop", "exit", "cancel", "close"]:
            return {"max_carbs": None}
        
        num = self.extract_number(tracker.latest_message.get("text", ""))
        if num is None:
            dispatcher.utter_message(text="🛑 I need a number! Please enter the max CARBOHYDRATES (% PDV).")
            return {"max_carbs": None, "max_fat": None, "max_protein": None}
        return {"max_carbs": num, "max_fat": None, "max_protein": None}

    # 3. Grassi
    def validate_max_fat(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        intent = tracker.latest_message.get("intent", {}).get("name")
        text = tracker.latest_message.get("text", "").lower()
        if intent == "stop" or text.strip() in ["stop", "exit", "cancel", "close"]:
            return {"max_fat": None}
        
        num = self.extract_number(tracker.latest_message.get("text", ""))
        if num is None:
            dispatcher.utter_message(text="🛑 I need a number! Please enter the max TOTAL FAT (% PDV).")
            return {"max_fat": None, "max_protein": None}
        return {"max_fat": num, "max_protein": None}

    # 4. Proteine
    def validate_max_protein(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        intent = tracker.latest_message.get("intent", {}).get("name")
        text = tracker.latest_message.get("text", "").lower()
        if intent == "stop" or text.strip() in ["stop", "exit", "cancel", "close"]:
            return {"max_protein": None}
        
        num = self.extract_number(tracker.latest_message.get("text", ""))
        if num is None:
            dispatcher.utter_message(text="🛑 I need a number! Please enter the max PROTEIN (% PDV).")
            return {"max_protein": None}
        return {"max_protein": num}


# =============================================================================
# SUBMIT FORM NUTRIZIONALE (Ricerca nel DB)
# =============================================================================
class ActionSubmitNutritionSearch(Action):
    def name(self) -> Text:
        return "action_submit_nutrition_search"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Recupera i target macros (già validati dalla Form!)
        target_cal = tracker.get_slot("max_calories")
        target_carbs = tracker.get_slot("max_carbs")
        target_fat = tracker.get_slot("max_fat")
        target_protein = tracker.get_slot("max_protein")

        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        matches = DATASET.copy()

        # =========================================================
        # CALCOLO DELLA "DISTANZA" (Errore Relativo)
        # Più il numero è vicino a 0, più la ricetta è perfetta!
        # Usiamo max(1, target) per evitare divisioni per zero se l'utente digita "0"
        # =========================================================
        matches['distance'] = (
            abs(matches['calories'] - target_cal) / max(1, target_cal) +
            abs(matches['carbohydrates'] - target_carbs) / max(1, target_carbs) +
            abs(matches['total_fat'] - target_fat) / max(1, target_fat) +
            abs(matches['protein'] - target_protein) / max(1, target_protein)
        )

        # Ordina in modo CRESCENTE per distanza (il più vicino a 0 vince) 
        # e decrescente per rating (a parità di distanza, vince la più buona)
        matches = matches.sort_values(by=['distance', 'rating_medio'], ascending=[True, False])
        
        # Prende le 5 ricette che si avvicinano di più all'obiettivo
        top_matches = matches.head(5)

        # Salviamo il testo in una variabile
        testo_risposta = f"🎯 SUCCESS! I found the recipes that best match your target macros:"
        
        buttons = []
        # Crea un bottone per ogni ricetta
        for index, row in top_matches.iterrows():
            r_name = row['name'].title()
            
            c = row['calories']
            carb = row['carbohydrates']
            fat = row['total_fat']
            pro = row['protein']
            
            # Aggiunta icona per layout verticale Telegram
            label = f"🥗 {r_name} ({c}kcal | C:{carb}% | F:{fat}% | P:{pro}%)"
            buttons.append({"title": label, "payload": f'/select_recipe{{"recipe_id":"{index}"}}'})
        
        # Invio combinato (Testo + Bottoni) in stile Telegram!
        dispatcher.utter_message(text=testo_risposta, buttons=buttons)

        # Pulizia slot
        return [
            SlotSet("max_calories", None), 
            SlotSet("max_carbs", None), 
            SlotSet("max_fat", None), 
            SlotSet("max_protein", None)
        ]

# =============================================================================
# VALIDAZIONE FORM FULL MEAL
# =============================================================================
class ValidateFullMealForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_full_meal_form"

    def validate_meal_tag(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        # Controllo se l'utente vuole fermarsi
        intent = tracker.latest_message.get("intent", {}).get("name")
        text = tracker.latest_message.get("text", "").lower()
        if intent == "stop" or text.strip() in ["stop", "exit", "cancel", "close"]:
            return {"meal_tag": None}

        # Prova a estrarre i tag usando le entità
        extracted_entities = [e["value"] for e in tracker.latest_message.get("entities", []) if e["entity"] in ["category", "meal_tag"]]
                
        # Prende il primo tag estratto (se ce n'è almeno uno)
        extracted_tag = extracted_entities[0].lower() if extracted_entities else None

        # Se non riesce ad estrarre nulla, prova a fare un parsing manuale (es. "I want a Mexican meal")
        if not extracted_tag:
            clean_text = text
            # Aggiunte parole extra (" menu", " food", " an ", " a ") per blindarlo
            for word in ["i want ", "make it ", "theme ", "diet ", " menu", " food", " an ", " a "]:
                clean_text = clean_text.replace(word, "")
            extracted_tag = clean_text.strip()
            
        # Se ancora non riesce ad estrarre nulla, mostra un messaggio di errore e resetta il tag
        if not extracted_tag:
            dispatcher.utter_message(text="🛑 I didn't catch that. Please provide a theme (e.g., 'Mexican').")
            return {"meal_tag": None}

        # --- VALIDAZIONE E FUZZY MATCHING ---
        if extracted_tag in ALL_UNIQUE_TAGS:
            return {"meal_tag": extracted_tag}
        else:
            if ALL_UNIQUE_TAGS:
                best_match, score = process.extractOne(extracted_tag, ALL_UNIQUE_TAGS, scorer=fuzz.ratio)
                if score >= 75:
                    print(f"✅ Validated Meal Tag: '{extracted_tag}' -> '{best_match}'")
                    return {"meal_tag": best_match}

        # Se fallisce anche il Fuzzy Match
        dispatcher.utter_message(text=f"🛑 I don't recognize '{extracted_tag}'. Give me a valid category (like 'Healthy', 'Winter').")
        return {"meal_tag": None}


# =============================================================================
# SUBMIT FORM FULL MEAL (Generazione del Menu)
# =============================================================================
class ActionSubmitFullMeal(Action):
    def name(self) -> Text:
        return "action_submit_full_meal"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        meal_tag = tracker.get_slot("meal_tag")
        
        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        # 1. Filtra tutto il database affinché contenga il TAG SCELTO
        matches = DATASET.copy()
        
        # Funzione di controllo del tema (tag) per ogni ricetta
        def check_theme(row_tag_str):
            try:
                recipe_tags = [x.lower().strip() for x in ast.literal_eval(row_tag_str)]
                return meal_tag in recipe_tags
            except:
                return False
                
        # Applica il filtro del tema (tag) al dataset
        theme_matches = matches[matches['tags'].apply(check_theme)]

        # 2. Struttura delle 5 Portate
        # Formato: (Nome Display, [lista_tag_accettati])
        courses = [
            ("🥗 Appetizer", ["appetizers"]),
            ("🍝 First Course", ["pasta", "rice"]),
            ("🥩 Main Course", ["main-dish"]),
            ("🍟 Side Dish", ["side-dishes"]),
            ("🍰 Dessert", ["desserts"])
        ]

        # Formatta il messaggio iniziale del menu
        msg = f"🍽️ **The Ultimate {meal_tag.title()} Menu** 🍽️\n\n"
        buttons = []

        # 3. Cerca la ricetta migliore per ogni portata
        for course_name, valid_course_tags in courses:
            
            # Funzione di controllo per verificare se una ricetta appartiene alla portata (controlla se ha ALMENO UNO dei tag validi)
            def check_course(row_tag_str):
                try:
                    recipe_tags = [x.lower().strip() for x in ast.literal_eval(row_tag_str)]
                    return any(t in recipe_tags for t in valid_course_tags)
                except:
                    return False
            
            # Filtra il database già scremato per il tema
            course_matches = theme_matches[theme_matches['tags'].apply(check_course)]
            
            # Se trova qualcosa...
            if not course_matches.empty:
                # Ordina per trovare la migliore in assoluto
                course_matches = course_matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
                top_recipe = course_matches.iloc[0]
                
                r_name = top_recipe['name'].title()
                r_rate = top_recipe['rating_medio']
                
                # Prendo l'ID (l'indice) per creare il bottone
                r_id = course_matches.index[0]
                
                msg += f"**{course_name}:** {r_name} ({r_rate}⭐)\n"
                
                # Crea un bottone rapido per permettere all'utente di aprire subito quella ricetta
                buttons.append({"title": f"See {course_name.split()[1]}", "payload": f'/select_recipe{{"recipe_id":"{r_id}"}}'})
            else:
                # Se non c'è nessuna ricetta per quella portata con quel tema
                msg += f"**{course_name}:** -\n"

        # 4. Invia il menu all'utente
        dispatcher.utter_message(text=msg)
        if buttons:
            dispatcher.utter_message(text="Tap a button below to get the full recipe for a specific course:", buttons=buttons)

        # Pulizia slot
        return [SlotSet("meal_tag", None)]

class ActionRandomRecipe(Action):
    def name(self) -> Text:
        return "action_random_recipe"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        # Seleziona una ricetta casuale
        random_recipe = DATASET.sample(n=1).iloc[0]

        r_name = random_recipe['name'].title()
        r_rate = random_recipe['rating_medio']
        r_id = random_recipe.name # L'indice del DataFrame è l'ID della ricetta

        msg = f"🎲 **Random Recipe:** {r_name} ({r_rate}⭐)\n\n"
        buttons = [{"title": "See Full Recipe", "payload": f'/select_recipe{{"recipe_id":"{r_id}"}}'}]

        dispatcher.utter_message(text=msg, buttons=buttons)
        return []

class ActionResetSvuotaFrigoForm(Action):
    def name(self) -> Text:
        return "action_reset_svuota_frigo_form"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Resetta tutti gli slot della form
        return [
            SlotSet("ingredient", None),
            SlotSet("time_limit", None),
            SlotSet("category", None)
        ]
    
class ActionResetNutritionSearchForm(Action):
    def name(self) -> Text:
        return "action_reset_nutrition_search_form"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Resetta tutti gli slot della form
        return [
            SlotSet("max_calories", None), 
            SlotSet("max_carbs", None), 
            SlotSet("max_fat", None), 
            SlotSet("max_protein", None)
        ]
    
class ActionResetFullMealForm(Action):
    def name(self) -> Text:
        return "action_reset_full_meal_form"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Resetta lo slot del tema
        return [SlotSet("meal_tag", None)]