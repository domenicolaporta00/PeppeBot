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

PERCORSO_DATASET = 'dataset/dataset_svuotafrigo_finale.csv'  # Assicurati che il percorso sia corretto
ALL_UNIQUE_TAGS = []
ALL_UNIQUE_INGREDIENTS = []
DATASET = None

# Carichiamo il dataset una volta sola all'avvio
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

    # --- 2. INDICIZZAZIONE INGREDIENTI (NUOVO) ---
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
    
class ActionSearchByCategory(Action):
    def name(self) -> Text:
        return "action_search_by_category"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ora user_input sarà una LISTA (es. ['vegan', 'italian'])
        user_input = tracker.get_slot("category")
        
        if not user_input:
            dispatcher.utter_message(text="❓ What category are you looking for? (e.g., Winter, Spicy, Vegan)")
            return []

        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        # Assicuriamoci che sia una lista (per sicurezza)
        if isinstance(user_input, str):
            user_input = [user_input]

        print(f"🔍 Categorie cercate dall'utente (raw): {user_input}")

        # Iniziamo col dataset completo
        matches = DATASET.copy()
        
        # Lista per tenere traccia dei tag validi trovati (per il messaggio finale)
        found_tags = []

        # --- CICLO DI FILTRAGGIO ---
        # Per ogni tag chiesto dall'utente, restringiamo i risultati
        for item in user_input:
            search_tag = item.lower().strip()
            
            # 1. Fuzzy Check per il singolo tag
            # Se il tag non è contenuto nel DB (controllo rapido), proviamo a correggerlo
            # Nota: qui usiamo una logica semplificata per velocità
            current_tag_matches = matches[matches['tags'].str.contains(search_tag, case=False, na=False, regex=False)]
            
            if current_tag_matches.empty and ALL_UNIQUE_TAGS:
                try:
                    best_match, score = process.extractOne(search_tag, ALL_UNIQUE_TAGS)
                    if score >= 65:
                        print(f"💡 Fuzzy Correction: '{search_tag}' -> '{best_match}'")
                        search_tag = best_match
                except:
                    pass
            
            # Aggiungiamo il tag (originale o corretto) alla lista dei confermati
            found_tags.append(search_tag)

            # 2. APPLICAZIONE FILTRO
            # Restringiamo il dataset `matches` solo alle righe che hanno QUESTO tag
            matches = matches[matches['tags'].str.contains(search_tag, case=False, na=False, regex=False)]
            
            # Se a un certo punto non rimane nulla (es. "Vegan" + "Steak"), fermiamoci
            if matches.empty:
                break

        # --- RISULTATI ---
        tags_str = " + ".join([f"**{t}**" for t in found_tags])
        
        if not matches.empty:
            matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
            count = len(matches)
            top_matches = matches.head(5)

            dispatcher.utter_message(text=f"🔍 I found {count} recipes matching {tags_str}! Here are the best ones:")
            
            buttons = []
            for index, row in top_matches.iterrows():
                r_name = row['name'].title()
                r_rate = row['rating_medio']
                title = f"{r_name} ({r_rate}⭐)"
                payload = f'/select_recipe{{"recipe_id":"{index}"}}'
                buttons.append({"title": title, "payload": payload})
            
            dispatcher.utter_message(buttons=buttons)
        
        else:
            # Messaggio intelligente: dice quali tag combinati non hanno prodotto risultati
            dispatcher.utter_message(text=f"😔 No recipes found matching ALL these criteria: {tags_str}. Try searching for just one of them.")
        
        # Resetta lo slot
        return [SlotSet("category", None)]
    
class ActionAskNutrition(Action):
    def name(self) -> Text:
        return "action_ask_nutrition"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Prendiamo tutti i possibili slot
        recipe_id = tracker.get_slot("recipe_id")
        recipe_name = tracker.get_slot("recipe_name")
        requested_nutrient = tracker.get_slot("nutrient")
        
        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        row = None # Qui metteremo la riga della ricetta trovata

        # --- 1. PRIORITÀ ASSOLUTA ALL'ID (Click dal Bottone) ---
        # Se abbiamo un ID, ignoriamo il nome e prendiamo la riga esatta.
        if recipe_id:
            try:
                r_index = int(recipe_id)
                # Controlliamo se l'indice è valido
                if 0 <= r_index < len(DATASET):
                    row = DATASET.iloc[r_index]
                    print(f"✅ Trovata ricetta via ID: {r_index} -> {row['name']}")
                else:
                    dispatcher.utter_message(text="⚠️ Invalid Recipe ID.")
                    return [SlotSet("recipe_id", None)]
            except ValueError:
                pass # Se l'ID non è un numero, proseguiamo con la ricerca per nome

        # --- 2. RICERCA PER NOME (Solo se non abbiamo trovato via ID) ---
        if row is None and recipe_name:
            search_term = recipe_name.lower().strip()
            
            # Ricerca ampia (contains)
            matches = DATASET[DATASET['name'].str.contains(search_term, case=False, na=False, regex=False)]
            
            # Fuzzy fallback
            if matches.empty and ALL_UNIQUE_TAGS:
                try:
                    all_names = DATASET['name'].tolist()
                    best_match, score = process.extractOne(search_term, all_names)
                    if score >= 60:
                        dispatcher.utter_message(text=f"Did you mean **{best_match}**? Checking... 🕵️")
                        matches = DATASET[DATASET['name'].str.contains(best_match, case=False, na=False, regex=False)]
                except:
                    pass

            if not matches.empty:
                # Ordiniamo
                matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
                unique_names = matches['name'].unique()
                
                # SE CI SONO AMBIGUITÀ -> MOSTRIAMO I BOTTONI CON L'ID
                if len(unique_names) > 1:
                    dispatcher.utter_message(text=f"🔍 I found multiple recipes for **'{recipe_name}'**. Select the exact one:")
                    
                    buttons = []
                    # Prendiamo i primi 5 risultati diversi
                    for index, r in matches.head(5).iterrows():
                        r_name = r['name'].title()
                        
                        # --- LA MODIFICA CHIAVE È QUI ---
                        # Il payload ora passa 'recipe_id' (che è l'indice), NON il nome.
                        # Passiamo anche 'nutrient' per ricordarci cosa voleva sapere l'utente (cal, sugar, ecc)
                        nutr_payload = f', "nutrient": "{requested_nutrient}"' if requested_nutrient else ''
                        
                        # Esempio: /ask_nutrition{"recipe_id": "123", "nutrient": "calories"}
                        payload = f'/ask_nutrition{{"recipe_id":"{index}"{nutr_payload}}}'
                        
                        buttons.append({"title": r_name, "payload": payload})
                    
                    dispatcher.utter_message(buttons=buttons)
                    return [] # Ci fermiamo qui e aspettiamo il click
                
                else:
                    # Match unico
                    row = matches.iloc[0]
            else:
                dispatcher.utter_message(text=f"😔 I couldn't find nutritional info for **{recipe_name}**.")
                return [SlotSet("recipe_name", None)]

        # --- 3. MOSTRA RISULTATI (Se abbiamo trovato 'row') ---
        if row is not None:
            r_name = row['name'].title()
            
            # MAPPING COLONNE
            column_map = {
                "calories": "calories", "total_fat": "total_fat", "fat": "total_fat",
                "sugar": "sugar", "sodium": "sodium", "protein": "protein",
                "saturated_fat": "saturated_fat", "saturated": "saturated_fat",
                "carbohydrates": "carbohydrates", "carbs": "carbohydrates"
            }

            if requested_nutrient:
                clean_nutrient = requested_nutrient.lower().replace(" ", "_")
                col_name = column_map.get(clean_nutrient, clean_nutrient)

                if col_name in row:
                    value = row[col_name]
                    unit = "kcal" if col_name == "calories" else "% PDV"
                    dispatcher.utter_message(text=f"📊 **{r_name}** contains **{value} {unit}** of {requested_nutrient}.")
                else:
                    dispatcher.utter_message(text=f"⚠️ Info about '{requested_nutrient}' not available.")
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

        # Resettiamo TUTTI gli slot per evitare conflitti futuri
        return [SlotSet("recipe_name", None), SlotSet("recipe_id", None), SlotSet("nutrient", None)]
    
class ActionAskCookingTime(Action):
    def name(self) -> Text:
        return "action_ask_cooking_time"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        recipe_id = tracker.get_slot("recipe_id")
        recipe_name = tracker.get_slot("recipe_name")
        
        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        row = None # Qui metteremo la riga trovata

        # --- 1. PRIORITÀ ID (Se clicco un bottone) ---
        if recipe_id:
            try:
                r_index = int(recipe_id)
                if 0 <= r_index < len(DATASET):
                    row = DATASET.iloc[r_index]
                else:
                    dispatcher.utter_message(text="⚠️ Invalid Recipe ID.")
                    return [SlotSet("recipe_id", None)]
            except ValueError:
                pass

        # --- 2. RICERCA PER NOME (Se non ho ID) ---
        if row is None and recipe_name:
            search_term = recipe_name.lower().strip()
            
            # Ricerca ampia
            matches = DATASET[DATASET['name'].str.contains(search_term, case=False, na=False, regex=False)]
            
            # Fuzzy fallback
            if matches.empty and ALL_UNIQUE_TAGS:
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
                    dispatcher.utter_message(text=f"⏱️ I found multiple recipes for **'{recipe_name}'**. Which one?")
                    
                    buttons = []
                    for index, r in matches.head(5).iterrows():
                        r_name = r['name'].title()
                        # Payload punta a questa azione ma con l'ID
                        payload = f'/ask_cooking_time{{"recipe_id":"{index}"}}'
                        buttons.append({"title": r_name, "payload": payload})
                    
                    dispatcher.utter_message(buttons=buttons)
                    return []
                
                else:
                    # Match unico
                    row = matches.iloc[0]
            else:
                dispatcher.utter_message(text=f"😔 I couldn't find cooking times for **{recipe_name}**.")
                return [SlotSet("recipe_name", None)]

        # --- 3. MOSTRA RISULTATO (Se ho trovato la riga) ---
        if row is not None:
            r_name = row['name'].title()
            r_minutes = row['minutes']
            
            # Formattazione carina del tempo
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

        # Assicuriamoci che sia una lista
        if isinstance(user_input, str):
            user_input = [user_input]

        print(f"🥦 Ingredienti cercati dall'utente (raw): {user_input}")

        # Iniziamo col dataset completo
        matches = DATASET.copy()
        
        # Lista per tenere traccia degli ingredienti validi trovati
        found_ingredients = []

        # --- CICLO DI FILTRAGGIO (Logica AND) ---
        for item in user_input:
            search_item = item.lower().strip()
            
            # A. Fuzzy Check sul singolo ingrediente
            # Cerchiamo se esiste nel DB o se va corretto usando ALL_UNIQUE_INGREDIENTS
            
            # Controllo rapido se c'è già un match esatto nel subset corrente
            current_matches = matches[matches['ingredients'].str.contains(search_item, case=False, na=False, regex=False)]
            
            # Se non troviamo nulla e abbiamo la lista globale, proviamo il Fuzzy
            if current_matches.empty and ALL_UNIQUE_INGREDIENTS:
                try:
                    best_match, score = process.extractOne(search_item, ALL_UNIQUE_INGREDIENTS)
                    # Soglia leggermente più alta per ingredienti (70-75) per evitare falsi positivi strani
                    if score >= 70:
                        print(f"💡 Fuzzy Ingredient Correction: '{search_item}' -> '{best_match}'")
                        search_item = best_match
                except:
                    pass
            
            # Aggiungiamo l'ingrediente (originale o corretto) alla lista dei confermati
            found_ingredients.append(search_item)

            # B. APPLICAZIONE FILTRO
            # Restringiamo il dataset `matches` alle sole righe che contengono questo ingrediente
            matches = matches[matches['ingredients'].str.contains(search_item, case=False, na=False, regex=False)]
            
            # Se a un certo punto non rimane nulla, fermiamoci
            if matches.empty:
                break

        # --- RISULTATI ---
        ing_str = " + ".join([f"**{i}**" for i in found_ingredients])
        
        if not matches.empty:
            # Ordiniamo per rating
            matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
            count = len(matches)
            top_matches = matches.head(5)

            dispatcher.utter_message(text=f"🍳 I found {count} recipes using {ing_str}! Here are the best ones:")
            
            buttons = []
            for index, row in top_matches.iterrows():
                r_name = row['name'].title()
                r_rate = row['rating_medio']
                title = f"{r_name} ({r_rate}⭐)"
                payload = f'/select_recipe{{"recipe_id":"{index}"}}'
                buttons.append({"title": title, "payload": payload})
            
            dispatcher.utter_message(buttons=buttons)
        
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
        
        extracted = [e["value"] for e in tracker.latest_message.get("entities", []) if e["entity"] == "ingredient"]
        
        if not extracted:
            text = tracker.latest_message.get("text", "").lower()
            for word in ["i have ", "use ", "some ", "only ", "want "]:
                text = text.replace(word, "")
            extracted = [i.strip() for i in text.replace(" and ", ",").split(",") if len(i.strip()) > 1]

        if not extracted:
            dispatcher.utter_message(text="🛑 I didn't catch anything! Please tell me the INGREDIENTS you want to use.")
            # SCUDO: Resettiamo tutto il resto se fallisce
            return {"ingredient": None, "time_limit": None, "category": None}

        valid_ingredients = []
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

        if not valid_ingredients:
            dispatcher.utter_message(text="🛑 I don't recognize those as ingredients. Please give me valid food items (e.g., chicken, eggs).")
            # SCUDO: Resettiamo tutto il resto se fallisce
            return {"ingredient": None, "time_limit": None, "category": None}

        # SUCCESSO: Salviamo gli ingredienti ma azzeriamo il tempo e la categoria per impedire salti!
        return {"ingredient": valid_ingredients, "time_limit": None, "category": None}

    # ==========================================
    # 2. VALIDAZIONE TEMPO
    # ==========================================
    def validate_time_limit(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        text = tracker.latest_message.get("text", "").lower()
        numbers = re.findall(r'\d+', text)
        
        if not numbers:
            dispatcher.utter_message(text="🛑 I need a number! How many MINUTES do you have?")
            # SCUDO: Se ha digitato roba a caso (es. "vegan"), impediamo che Rasa lo salvi come categoria
            return {"time_limit": None, "category": None}
            
        # SUCCESSO: Salviamo il tempo, ma azzeriamo la categoria per forzare il passaggio 3
        return {"time_limit": int(numbers[0]), "category": None}

    # ==========================================
    # 3. VALIDAZIONE CATEGORIE / TAGS
    # ==========================================
    def validate_category(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        
        text = tracker.latest_message.get("text", "").lower()
        
        if text in ["none", "nothing", "no", "skip", "any", "i don't care"]:
            return {"category": ["none"]}

        extracted = [e["value"] for e in tracker.latest_message.get("entities", []) if e["entity"] == "category"]
        if not extracted:
            extracted = [c.strip() for c in text.replace(" and ", ",").split(",") if len(c.strip()) > 1]

        if not extracted:
            dispatcher.utter_message(text="🛑 I didn't catch anything. Please provide a tag (like 'Vegan') or type 'none'.")
            return {"category": None}

        valid_tags = []
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

        # 1. Recuperiamo i dati (già perfetti e validati dalla Form!)
        ingredients = tracker.get_slot("ingredient")
        time_limit = tracker.get_slot("time_limit")
        categories = tracker.get_slot("category")

        if DATASET is None:
            dispatcher.utter_message(text="⚠️ Database Error.")
            return []

        matches = DATASET.copy()

        # 2. FILTRO TEMPO (Lo facciamo per primo perché è il calcolo più veloce)
        if time_limit:
            matches = matches[matches['minutes'] <= int(time_limit)]

        # 3. FILTRO INGREDIENTI (Ricerca Esatta nell'Array)
        if not matches.empty and ingredients:
            def check_ingredients(row_ing_str):
                try:
                    # Converte la stringa "['olive', 'garlic']" in una VERA lista Python
                    recipe_ings = [x.lower().strip() for x in ast.literal_eval(row_ing_str)]
                    
                    # Controlla che TUTTI gli ingredienti cercati siano nella lista
                    for search_item in ingredients:
                        # Qui sta la magia: "olive" == "olive" (True), "olive" == "olive oil" (False)
                        if search_item.lower() not in recipe_ings:
                            return False
                    return True
                except:
                    return False
                    
            matches = matches[matches['ingredients'].apply(check_ingredients)]

        # 4. FILTRO CATEGORIE / TAGS (Ricerca Esatta nell'Array)
        if not matches.empty and categories and categories != ["none"]:
            def check_tags(row_tag_str):
                try:
                    # Stessa logica degli ingredienti per evitare che "vegan" matchi con "non-vegan"
                    recipe_tags = [x.lower().strip() for x in ast.literal_eval(row_tag_str)]
                    for cat in categories:
                        if cat.lower() not in recipe_tags:
                            return False
                    return True
                except:
                    return False
                    
            matches = matches[matches['tags'].apply(check_tags)]

        # --- 5. MOSTRA I RISULTATI ---
        ing_display = ", ".join(ingredients) if ingredients else "any ingredients"
        cat_display = "" if not categories or categories == ["none"] else f" and tags ({', '.join(categories)})"
        
        if not matches.empty:
            matches = matches.sort_values(by=['rating_medio', 'num_voti'], ascending=[False, False])
            count = len(matches)
            top_matches = matches.head(5)

            dispatcher.utter_message(text=f"🎉 SUCCESS! I found {count} recipes using **{ing_display}**, under **{time_limit} mins**{cat_display}:")
            
            buttons = []
            for index, row in top_matches.iterrows():
                r_name = row['name'].title()
                buttons.append({"title": f"{r_name} ({row['minutes']}m)", "payload": f'/select_recipe{{"recipe_id":"{index}"}}'})
            
            dispatcher.utter_message(buttons=buttons)
        else:
            dispatcher.utter_message(text=f"😔 I'm sorry, I couldn't find any recipe combining **{ing_display}** under **{time_limit} minutes**{cat_display}. The fridge is too empty!")

        # 6. PULIZIA TOTALE (Svuota gli slot per la prossima ricerca)
        return [SlotSet("ingredient", None), SlotSet("time_limit", None), SlotSet("category", None)]