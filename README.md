# MacAmbientSync

MacAmbientSync è un'applicazione desktop per macOS che cattura in tempo reale i colori predominanti del tuo schermo e li sincronizza istantaneamente con le luci RGB di **Home Assistant** (lampade, strisce LED, barre luminose). Progettata per avere un impatto quasi nullo sulla CPU (<1%) e una resa cromatica vivida e cinematografica.

---

## ✨ Funzionalità Principali

* 🖥️ **Interfaccia Grafica Dedicata (GUI)**: Un'applicazione desktop completa con finestra nativa su macOS, controlli immediati, anteprima del colore in tempo reale e gestione completa dei parametri senza dover modificare file manualmente.
* 🛑 **Chiusura Completa e Pulita**: Quando chiudi la finestra (o usi `Cmd+Q` / `Chiudi`), l'app e tutti i thread di cattura e trasmissione vengono interrotti immediatamente senza processi residui in background.
* 🎨 **Anteprima Live Colore e Luminosità**: Mostra in diretta il colore dominante rilevato a schermo, i valori RGB, il codice HEX e la percentuale di luminosità inviata a Home Assistant.
* ⚡ **Verifica Connessione Integrata**: Pulsante "Verifica Connessione" per testare istantaneamente il server Home Assistant, il Token e l'Entity ID della lampada con feedback visivo.
* 📺 **Rilevamento Bande Nere (Letterbox)**: Esclude automaticamente le bande nere dei film (es. formato 21:9) per calcolare solo i colori effettivi della scena.
* ⚡ **Prestazioni e CPU < 1%**: Utilizza un downscaling rapido e l'exponential moving average (EMA) per transizioni fluide e filtri anti-spam sulle richieste di rete.
* 🖥️ **Supporto Multi-Monitor**: Scegli quale monitor sincronizzare (display principale, monitor secondario o display combinato).

---

## 🚀 Come Eseguire l'Applicazione

### 1. Requisiti e Installazione Dipendenze
Assicurati di avere Python 3 installato. Crea un virtual environment e installa i pacchetti necessari:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Avvio dell'App Desktop
Per avviare l'applicazione con interfaccia grafica:

```bash
source venv/bin/activate
python3 app.py
```

### 3. Configurazione
All'interno dell'app:
1. Nella scheda **🏠 Home Assistant**:
   - Inserisci l'URL di Home Assistant (es. `http://192.168.1.100:8123`)
   - Inserisci il tuo **Long-Lived Access Token** (generabile dal tuo profilo su Home Assistant -> Token di accesso a lunga durata)
   - Inserisci l'**Entity ID** della tua lampada (es. `light.salotto_lampada`)
   - Clicca su **⚡ Verifica Connessione** per assicurarti che la configurazione sia corretta.
2. Nelle altre schede puoi personalizzare il monitor, gli FPS di campionamento, la rimozione delle bande nere e i boost di saturazione/luminosità.
3. Clicca su **💾 Salva Configurazione** e poi su **▶ Avvia Sincronizzazione**!

---

## 📦 Compilazione come App macOS (.app)

Per generare il file `MacAmbientSync.app` autonomo:

```bash
source venv/bin/activate
pip install py2app
python setup.py py2app
```

L'applicazione compilata sarà disponibile nella cartella `dist/MacAmbientSync.app`.
