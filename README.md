# MacAmbientSync

MacAmbientSync è una comoda App per macOS (con icona nella barra dei menu) che cattura lo schermo del Mac in tempo reale, calcola il colore dominante o medio della scena e sincronizza una lampada RGB o strip LED collegata a Home Assistant. Ottimizzato per avere un carico quasi nullo sulla CPU.

## Caratteristiche

*   **App nativa Menu Bar**: un'icona nella barra di stato in alto a destra per avviare/fermare la sincronizzazione o modificare le impostazioni.
*   **Bassissimo impatto CPU**: utilizza un downscaling estremo prima del calcolo del colore per garantire un utilizzo della CPU inferiore all'1%.
*   **Colori vividi**: applica un boost della saturazione e luminosità (configurabile) per evitare effetti di luce "sbiadita".
*   **Rimozione bande nere**: rileva e ignora in automatico il formato "letterbox" (es. film in 21:9).
*   **Smoothing ed efficienza**: utilizza una media esponenziale per transizioni colore morbide ed evita chiamate ad HA se il colore varia di poco.

## Installazione per l'Utente Finale

1. Scarica e unzippa `MacAmbientSync.app` dall'ultima release.
2. Sposta l'App nella cartella **Applicazioni**.
3. Clicca sull'icona della tavolozza 🎨 nella barra dei menu.
4. Clicca su **Edit Config...** per configurare:
   * `url`: l'indirizzo del tuo Home Assistant (es. `http://192.168.1.100:8123`)
   * `token`: il tuo Long-Lived Access Token di Home Assistant
   * `entity_id`: l'entità della lampada (es. `light.lampada_salotto`)
5. Clicca su **Start Sync**! L'icona diventerà 🔴 per indicare che la cattura è in corso.

## Compilare l'App (Per Sviluppatori)

Se vuoi compilare l'app tu stesso partendo dal codice sorgente:

1.  Clona il repository.
2.  Crea un ambiente virtuale e installa le dipendenze:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    pip install py2app
    ```
3.  Esegui il comando di build:
    ```bash
    python setup.py py2app
    ```
4.  Troverai la tua applicazione pronta nella cartella `dist/MacAmbientSync.app`.

## Configurazione Avanzata

Nel file `config.yaml` (accessibile dal menu `Edit Config...`) è possibile regolare vari parametri:

*   `fps`: Frequenza di campionamento. 3-5 Hz è spesso ottimale.
*   `monitor_index`: Quale monitor catturare (utile se usi schermi esterni).
*   `saturation_boost`: Valore > 1 per esaltare i colori.
*   `smoothing_factor`: Valore più basso (es. 0.2) per transizioni morbide, più alto (es. 0.8) per cambi rapidi.
