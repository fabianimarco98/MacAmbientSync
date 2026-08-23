# Mac Screen Ambient Sync for Home Assistant

Cattura lo schermo del Mac in tempo reale, calcola il colore dominante o medio della scena (con saturazione cinematografica e rimozione delle bande nere) e sincronizza una lampada RGB o strip LED collegata a Home Assistant. Ottimizzato per avere un carico quasi nullo sulla CPU del Mac.

## Caratteristiche

*   **Bassissimo impatto CPU**: utilizza un downscaling estremo prima del calcolo del colore per garantire un utilizzo della CPU inferiore all'1%.
*   **Colori vividi**: applica un boost della saturazione e luminosità (configurabile) per evitare effetti di luce "sbiadita".
*   **Rimozione bande nere**: rileva e ignora in automatico il formato "letterbox" (es. film in 21:9) così il nero non altera il colore dei bordi.
*   **Smoothing ed efficienza**: utilizza una media esponenziale per transizioni colore morbide ed evita chiamate di rete inutili ad Home Assistant se il colore varia di poco.

## Requisiti

*   Python 3 (e un ambiente macOS)
*   Un'istanza di Home Assistant accessibile dalla rete locale
*   Un Long-Lived Access Token per Home Assistant

## Installazione e Avvio Rapido

1.  Clona il repository o scarica i file in una cartella.
2.  Copia il file di configurazione di esempio:
    ```bash
    cp config.example.yaml config.yaml
    ```
3.  Modifica `config.yaml` inserendo:
    *   L'indirizzo del tuo Home Assistant (`url`)
    *   Il tuo Long-Lived Access Token (`token`)
    *   L'identificativo della tua lampada RGB (`entity_id`)
4.  Esegui lo script:
    *   Fai doppio clic su `start_ambient_sync.command` (creerà automaticamente l'ambiente virtuale e avvierà la sincronizzazione).
    *   *Oppure*, da terminale:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        python screen_sync.py
        ```

## Configurazione Avanzata

Nel file `config.yaml` è possibile regolare vari parametri:

*   `fps`: Frequenza di campionamento. 3-5 Hz è spesso ottimale per evitare di sovraccaricare la rete Wi-Fi/Zigbee delle lampade.
*   `monitor_index`: Quale monitor catturare (utile se usi schermi esterni).
*   `saturation_boost`: Valore > 1 per esaltare i colori e rendere l'effetto più cinematografico.
*   `smoothing_factor`: Un valore più basso (es. 0.2) rende i passaggi molto morbidi, uno più alto (es. 0.8) reagisce istantaneamente ma può sembrare "a scatti".
