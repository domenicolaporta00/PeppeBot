# PeppeBot

Il seguente progetto consiste nello sviluppo di un chatbot attraverso l'utilizzo del framework Rasa. Tale lavoro si inserisce nell'ambito del corso di Data Science (Corso di Laurea Magistrale di Ingegneria Informatica e dell'Automazione presso UNIVPM).

## 💡 Come nasce l'idea

Il progetto affonda le sue radici in **[GreenMarket](https://github.com/IzziGiuseppe/GreenMarket)**, un'applicazione mobile sviluppata nell'ambito del corso di Programmazione Mobile. All'interno dell'app era presente una funzionalità base che permetteva agli utenti di cercare ricette a partire da un singolo ingrediente presente nel loro carrello. 

Partendo da questo spunto, è nata l'esigenza di trasformare una semplice barra di ricerca in un vero e proprio **Assistente Culinario Intelligente**. Il progetto rappresenta un'evoluzione totale della funzionalità originale sotto due punti di vista fondamentali:

### 1. Evoluzione dei Requisiti (Da Ricerca a Consulenza)
L'obiettivo non è più limitarsi a rispondere alla domanda *"Cosa faccio con questo ingrediente?"*. Il sistema è stato ampliato per gestire un'esperienza culinaria a 360 gradi. Le nuove funzionalità includono:
* **Svuota Frigo Intelligente:** Ricerca multi-ingrediente combinata con limiti di tempo e preferenze dietetiche.
* **Consulenza Nutrizionale:** Ricerca e filtraggio avanzato delle ricette basato su target specifici di macronutrienti (Calorie, Carboidrati, Grassi, Proteine).
* **Pianificazione Menu:** Generazione dinamica di un menu completo a 5 portate basato su un tema specifico (es. Vegano, Messicano, Comfort Food).

### 2. Evoluzione Tecnologica (Da Scripting a Deep Learning)
Nella versione originale di GreenMarket, la ricerca si basava su un semplice algoritmo procedurale (es. *controlla se la stringa 'X' è presente nell'array degli ingredienti 'Y'*). 

Per questo progetto, il paradigma è stato completamente stravolto passando all'**Intelligenza Artificiale e al Natural Language Processing (NLP)**.
Attraverso l'implementazione del framework **Rasa**, il bot non esegue più ricerche meccaniche, ma è in grado di:
* Comprendere il linguaggio naturale dell'utente (NLU) estraendo entità complesse.
* Gestire il contesto della conversazione grazie alla memoria a breve termine (Tracker).
* Prevedere l'azione successiva più appropriata utilizzando modelli di Deep Learning addestrati su storie e flussi conversazionali reali.

## ✨ Funzionalità Chiave

PeppeBot è stato progettato per essere un assistente culinario completo. Ecco tutto ciò che è in grado di fare:

**1. Ricerca "Svuota Frigo"** 🧊
Trova la ricetta ideale in base agli ingredienti che hai a disposizione, al tuo limite di tempo e alle tue preferenze dietetiche (gestito tramite Form interattiva).
> _Try saying:_ "What can I cook today?" or "Empty fridge"

**2. Ricerca Fitness & Macros** 🥗
Filtra e calcola matematicamente le migliori ricette in base ai tuoi obiettivi specifici di calorie, carboidrati, grassi e proteine.
> _Try saying:_ "Suggest me a recipe by macros" or "can you recommend a recipe based on nutritional values?"

**3. Pianificatore di Menu Completo** 🍽️
Costruisce dinamicamente un menu completo di 5 portate (dall'antipasto al dolce) basato su un tema specifico scelto dall'utente.
> _Try saying:_ "I want a full course meal" or "Suggest a full menu"

**4. Ricerca per Nome** 🔎
Trova un piatto specifico ricercandolo all'interno del database, gestendo anche eventuali ambiguità tramite pulsanti interattivi.
> _Try saying:_ "Search for Carbonara"

**5. Ricerca per Categoria** 🍰
Suggerisce le migliori ricette appartenenti a una specifica categoria o dieta (es. dessert, vegano, invernale).
> _Try saying:_ "I want a dessert" or "Show me vegan recipes"

**6. Ricette Più Votate** ⭐
Mostra la classifica delle ricette con le valutazioni più alte e il maggior numero di recensioni da parte degli utenti.
> _Try saying:_ "Show me the best recipes"

**7. Informazioni Nutrizionali** 📊
Fornisce i dettagli precisi su nutrienti e calorie (es. percentuale di grassi, zuccheri, proteine) partendo dal nome di un piatto.
> _Try saying:_ "Show me the calories for Carbonara", "Carbs in Pizza" or "What are the macros for Lasagna?"

**8. Tempi di Cottura** ⏱️
Indica esattamente quanti minuti sono necessari per preparare e cucinare un piatto specifico.
> _Try saying:_ "How long does it take to cook Tiramisu?"

**9. Ricerca per Ingredienti** 🥕
Suggerisce ricette eccellenti che contengono gli specifici ingredienti che l'utente desidera consumare.
> _Try saying:_ "Recipes with chicken and mushrooms"

**10. Ricetta Casuale** 🎲
Sfrutta la funzionalità randomica per sorprendere l'utente con un piatto a caso quando è a corto di idee.
> _Try saying:_ "Give me a random dish" or "Surprise me with a recipe"


## 🛠️ Tecnologie Utilizzate

Il progetto si basa su uno stack moderno orientato al Machine Learning e all'analisi dei dati:

* **[Rasa Open Source](https://rasa.com/):** Il framework core utilizzato per l'NLU (Natural Language Understanding) e per la gestione del dialogo (Core). Permette al bot di estrarre intenti ed entità, gestire Form complesse e imparare dai flussi conversazionali (Stories) anziché seguire rigidi alberi decisionali.
* **Python 3:** Linguaggio principale utilizzato per lo sviluppo della logica di business e del server delle Custom Actions.
* **[Pandas](https://pandas.pydata.org/):** Libreria fondamentale impiegata all'interno delle azioni personalizzate per la gestione, l'esplorazione e il filtraggio avanzato e performante del dataset delle ricette in formato CSV.
* **Fuzzy Matching (`thefuzz` / `fuzzywuzzy`):** Algoritmo basato sulla distanza di Levenshtein, implementato per creare meccanismi di tolleranza agli errori. Permette al bot di capire e correggere automaticamente nomi di ricette, categorie o ingredienti digitati in modo impreciso.
* **Telegram API & Ngrok:** Utilizzati per esporre il server locale (tramite Webhook) e interfacciare il chatbot con l'applicazione reale di messaggistica Telegram, fornendo un'interfaccia ricca con pulsanti interattivi.

## 📂 Struttura del Progetto

Il repository segue l'architettura standard di un progetto **Rasa**, suddiviso logicamente tra l'addestramento del modello NLP e il server delle azioni in Python.



```text
PeppeBot/
│
├── data/
│   ├── nlu.yml          # Dati di addestramento NLU (Intenti, Entità ed esempi di frasi utente)
│   ├── stories.yml      # Copioni di conversazione per l'addestramento del Core
│   └── rules.yml        # Regole fisse per attivare le Form (Svuota Frigo, Macro, ecc.) e gestire i Fallback
│
├── actions/
│   └── actions.py       # Il cuore logico del bot: contiene tutte le Custom Actions in Python (ricerche Pandas, logica matematica per macros, gestione bottoni Telegram)
│
├── domain.yml           # L'inventario del bot: definisce tutti gli intenti, gli slot (memoria), le entità, le Form e i template di risposta (utterances)
├── config.yml           # Configurazione della pipeline NLU (tokenizers, featurizers) e delle policy del Core (TED, RulePolicy)
├── credentials.yml      # File di configurazione per l'integrazione con i canali di messaggistica (es. Token API di Telegram)
├── endpoints.yml        # Vi vengono configurati gli endpoint per connettersi a servizi esterni, come, ad esempio, un server per l’esecuzione delle azioni personalizzate (API REST, etc.)
└── README.md            # Questo file
