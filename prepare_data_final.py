import pandas as pd
import ast
import numpy as np
import csv

# --- FUNZIONI DI UTILITÀ ---

def clean_list_column(text):
    """Converte stringhe tipo "['a', 'b']" in liste Python reali."""
    try:
        return ast.literal_eval(text)
    except:
        return []

def clean_nutrition(text):
    """Estrae i 7 valori nutrizionali dalla stringa."""
    try:
        clean_text = text.replace('[', '').replace(']', '')
        parts = clean_text.split(',')
        return [float(x.strip()) for x in parts]
    except:
        return [0.0] * 7

def fix_tags_list(tag_list):
    """Sostituisce tag vuoti [''] con ['general']."""
    cleaned = [t for t in tag_list if t != '' and t != ' ']
    if len(cleaned) == 0:
        return ['general']
    return cleaned

# --- INIZIO SCRIPT ---

print("⏳ 1. Caricamento dei file RAW...")
recipes = pd.read_csv('RAW_recipes.csv')
interactions = pd.read_csv('RAW_interactions.csv')

# ---------------------------------------------------------
# CALCOLO STATISTICHE VOTI
# ---------------------------------------------------------
print("⏳ 2. Calcolo Statistiche Voti...")
stats = interactions.groupby('recipe_id').agg({
    'rating': ['mean', 'count']
}).reset_index()
stats.columns = ['id', 'rating_medio', 'num_voti']
stats['rating_medio'] = stats['rating_medio'].round(1)

df = pd.merge(recipes, stats, left_on='id', right_on='id', how='left')
df['rating_medio'] = df['rating_medio'].fillna(0)
df['num_voti'] = df['num_voti'].fillna(0)

# ---------------------------------------------------------
# PULIZIA STRUTTURALE
# ---------------------------------------------------------
print("⏳ 3. Pulizia colonne complesse (Liste e Nutrizione)...")

nutrition_data = df['nutrition'].apply(clean_nutrition).tolist()
nutrition_df = pd.DataFrame(nutrition_data, columns=[
    'calories', 'total_fat', 'sugar', 'sodium', 'protein', 'saturated_fat', 'carbohydrates'
])
df = pd.concat([df, nutrition_df], axis=1)

df['ingredients'] = df['ingredients'].apply(clean_list_column)
df['steps'] = df['steps'].apply(clean_list_column)
df['tags'] = df['tags'].apply(clean_list_column)
df['tags'] = df['tags'].apply(fix_tags_list)

# ---------------------------------------------------------
# APPLICAZIONE FIX SPECIFICI E PULIZIA DESCRIZIONI
# ---------------------------------------------------------
print("⏳ 4. Applicazione Fix Manuali e Pulizia Testi...")

# Fix ID 368257 (Senza nome)
df.loc[df['id'] == 368257, 'name'] = "Zesty Lemon-Honey Herb Dressing"

# --- NUOVA GESTIONE DESCRIZIONI (Blacklist) ---
descrizione_default = "No detailed description available, but this dish looks delicious!"

# 1. Riempiamo i NULL/NaN
df['description'] = df['description'].fillna(descrizione_default)

# 2. Lista di stringhe "spazzatura" identificate da te
blacklist_garbage = [
    "--", "----", "-----", ",", ",,,", ",..", "..", "...", 
    "(;", "***", "-------------", "........"
]

# 3. Sostituzione se la descrizione è nella blacklist O se è lunga 1 carattere
mask_garbage = df['description'].isin(blacklist_garbage)
mask_single_char = df['description'].str.len() == 1

df.loc[mask_garbage | mask_single_char, 'description'] = descrizione_default

print(f"   - Descrizioni 'garbage' sostituite: {mask_garbage.sum()}")
print(f"   - Descrizioni di 1 carattere sostituite: {mask_single_char.sum()}")

# === FIX SPECIFICO ID 506039 (IL "2013") ===
target_id = 506039
print(f"\n   --- DEBUG SPECIALE ID {target_id} ---")

# Verifichiamo se esiste e stampiamo il valore attuale
valore_attuale = df.loc[df['id'] == target_id, 'description'].values
if len(valore_attuale) > 0:
    print(f"   VALORE TROVATO: '{valore_attuale[0]}'")
    
    # SOVRASCRITTURA FORZATA
    df.loc[df['id'] == target_id, 'description'] = descrizione_default
    print(f"   -> FIX APPLICATO: Descrizione sovrascritta con il testo di default.")
else:
    print(f"   ATTENZIONE: ID {target_id} non trovato (forse filtrato prima?).")

# Fix Apostrofo Iniziale (CSV Injection)
mask_apostrofo = df['description'].str.startswith("'", na=False)
if mask_apostrofo.sum() > 0:
    df.loc[mask_apostrofo, 'description'] = df.loc[mask_apostrofo, 'description'].str[1:]
    print(f"   - Rimossi apostrofi iniziali da {mask_apostrofo.sum()} ricette.")

# ---------------------------------------------------------
# FILTRAGGIO DATASET
# ---------------------------------------------------------
print("⏳ 5. Applicazione Filtri di Qualità...")

totale_iniziale = len(df)

# Filtri definitivi concordati
f_min_zero = (df['minutes'] > 0)
f_min_max = (df['minutes'] <= 300000) # Include i liquori/fermentati
f_calories = (df['calories'] < 10000) # Via Moonshine e errori porzioni
f_no_bad_id = (df['id'] != 176767)    # Via ricetta 0 steps
f_has_votes = (df['num_voti'] > 0)
f_has_ingr = (df['ingredients'].str.len() > 0)

df_clean = df[
    f_min_zero & f_min_max & f_calories & 
    f_no_bad_id & f_has_votes & f_has_ingr
].copy()

diff = totale_iniziale - len(df_clean)
print(f"   - Rimossi {diff} record non validi.")

# ---------------------------------------------------------
# SALVATAGGIO FINALE
# ---------------------------------------------------------
print("⏳ 6. Preparazione file finale...")

cols_to_keep = [
    'name', 'id', 'minutes', 'contributor_id', 'submitted', 
    'n_steps', 'steps', 'description', 'ingredients', 'n_ingredients',
    'rating_medio', 'num_voti',
    'calories', 'total_fat', 'sugar', 'sodium', 'protein', 'saturated_fat', 'carbohydrates',
    'tags'
]
df_final = df_clean[cols_to_keep]

output_filename = 'dataset_svuotafrigo_finale.csv'
df_final.to_csv(output_filename, index=False, quoting=csv.QUOTE_NONNUMERIC)

print(f"\n✅ FATTO! File '{output_filename}' generato con successo.")
print(f"   Numero ricette finali: {len(df_final)}")