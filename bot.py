import os
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import gspread
from google.oauth2.service_account import Credentials
import urllib.request
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IT_TZ = ZoneInfo("Europe/Rome")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
LUCA_CHAT_ID = os.environ.get("LUCA_CHAT_ID", "")
SHEET_ID = "1JwzOe8PTibniJtZbgM9OgboianmXiuf4PIvD3By6Wz8"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CLAUDE_SYSTEM = """Sei l'assistente personale di Luca Puleo, un ragazzo italiano di 20 anni che da +3 anni lavora nel mondo online e dei bonus app. Ha aiutato +400 persone a guadagnare i primi soldi online.

Il tuo compito è assistere i lead nel flusso di qualificazione, rispondere alle loro domande e guidarli verso il contatto con Luca.

INFORMAZIONI SUI BONUS APP:
- Sono applicazioni gratuite (banche, fintech) che pagano bonus di benvenuto per nuove registrazioni
- Non serve alcun investimento, si parte da 0
- Serve essere maggiorenni con documento d'identità valido
- Mediamente 5-10 minuti per app, si possono spalamare su più giorni
- I bonus arrivano direttamente sull'app, solitamente in pochi giorni
- Una volta ricevuti Luca spiega come trasferirli sul conto principale
- Guadagno medio totale: +150€ con tutte le app
- Luca guadagna quanto il lead (stessi bonus per invitato e invitante)
- App disponibili: REVOLUT (15€), BBVA (10€), ISYBANK (30€ buono Amazon), BUDDYBANK (50€), CREDIT AGRICOLE (50€ buono Amazon), KRAK (10$)
- IsyBank è di Intesa SanPaolo

REGOLE FONDAMENTALI:
1. Non serve investimento, deposito, carta di credito — tutto gratis
2. Per domande fiscali/legali/ISEE/sussidi → "Per queste domande informati con il tuo commercialista"
3. Per dettagli tecnici sulle singole app → "Ne parlerai con Luca"
4. Per orari/tempistiche contatto Luca → "Ti contatterà il prima possibile"
5. Non dare MAI informazioni false o non confermate
6. Mantieni sempre un tono amichevole, diretto, rassicurante
7. Alla fine di ogni risposta riporta SEMPRE il lead alla domanda del flusso corrente
8. Non fare mai domande multiple — una sola risposta chiara
9. Rispondi SEMPRE in italiano
10. Tieni le risposte brevi e dirette — max 3-4 righe

TONO: amichevole, diretto, rassicurante, professionale. Mai eccessivamente formale."""

async def ask_claude(state: dict, user_message: str, step: str) -> str:
    """Chiama Claude API per gestire casi non previsti"""
    try:
        domanda = {
            "conosce_bonus": "Stai chiedendo al lead: Sai come funzionano i bonus app?",
            "dopo_spiegazione": "Hai appena spiegato i bonus app al lead e stai aspettando che voglia procedere.",
            "dopo_spiegazione_attesa": "Stai aspettando che il lead voglia procedere con le domande.",
            "ha_fatto_app": "Stai chiedendo al lead: Hai già fatto qualche app in passato?",
            "quali_app": "Hai mandato la lista delle app disponibili e stai chiedendo: Hai già fatto qualcuna di queste app?",
            "messaggio_finale": "Stai chiedendo al lead: C'è qualcosa che vorresti far sapere a Luca prima di iniziare?",
        }.get(step, "Stai gestendo la conversazione con il lead.")

        storico = []
        if state.get("conosce_bonus_risposta"):
            storico.append(f"- Sa cosa sono i bonus app: '{state['conosce_bonus_risposta']}'")
        if state.get("ha_fatto_app_risposta"):
            storico.append(f"- Ha già fatto app: '{state['ha_fatto_app_risposta']}'")
        if state.get("quali_app_risposta"):
            storico.append(f"- App già fatte: '{state['quali_app_risposta']}'")

        storico_str = "\n".join(storico) if storico else "Nessuna risposta ancora"
        nome = state.get("nome", "il lead")

        user_prompt = f"""Il lead si chiama {nome}.

Step corrente: {domanda}

Risposte già date dal lead:
{storico_str}

Messaggio attuale del lead: "{user_message}"

Rispondi in modo naturale e alla fine riporta il lead alla domanda corrente del flusso."""

        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 300,
            "system": CLAUDE_SYSTEM,
            "messages": [{"role": "user", "content": user_prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["content"][0]["text"]

    except Exception as e:
        logger.error(f"Errore Claude API: {e}")
        return None

GOOGLE_CREDS = {
    "type": "service_account",
    "project_id": os.environ.get("GOOGLE_PROJECT_ID"),
    "private_key_id": os.environ.get("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.environ.get("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ.get("GOOGLE_CLIENT_X509_CERT_URL"),
    "universe_domain": "googleapis.com"
}

BONUS_LIST = ["REVOLUT", "BBVA", "ISYBANK", "BUDDYBANK", "CREDIT AGRICOLE", "KRAK"]

# ─── STORAGE ─────────────────────────────────────────────────────
paused_leads = set()
all_leads = []
orange_leads = []
pending_messages = {}
global_states = {}

LISTA_APP = (
    "*BONUS ATTIVI*\n\n"
    "*__REVOLUT__*\n15€\n\n"
    "*__BBVA__*\n10€\n\n"
    "*__ISYBANK__*\n30€ BUONO AMAZON\n\n"
    "*__BUDDYBANK__*\n50€\n\n"
    "*__CREDIT AGRICOLE__*\n50€ BUONO AMAZON\n\n"
    "*__KRAK__*\n10$\n\n"
    "Hai già fatto qualcuna di queste app?"
)

def append_lead_to_sheet(nome, username, link):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(GOOGLE_CREDS, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1
        data = datetime.now(IT_TZ).strftime("%d/%m/%Y")
        sheet.append_row([data, nome, username, link], value_input_option="USER_ENTERED")
    except Exception as e:
        logger.error(f"Errore Google Sheets: {e}")

# ══════════════════════════════════════════════════════════════════
# CASISTICHE
# ══════════════════════════════════════════════════════════════════

AFFERMATIVO = {
    # Classici
    "si", "sì", "ok", "okay", "va bene", "vabene", "vai", "certo",
    "sisi", "sì sì", "ok ok", "perfetto", "andiamo", "dai", "sure",
    "assolutamente", "esatto", "confermo", "già", "appunto",
    "esattamente", "precisamente", "giusto", "corretto",
    "capito", "chiaro", "ho capito", "certamente", "naturalmente",
    "ovviamente", "yes", "yep", "yup", "yeah", "oki", "okei", "okey",
    "più o meno", "piu o meno", "ne ho sentito parlare",
    "ho sentito parlare", "credo di sì", "credo di si",
    "penso di sì", "penso di si", "vagamente", "in parte",
    "abbastanza", "quasi", "credo", "penso",
    "già sentito", "mi sembra di sì", "mi sembra di si",
    "ho visto qualcosa", "ne ho letto", "qualcosa ho capito",
    "mi ricordo qualcosa", "un po", "un poco",
    "tipo sì", "tipo si", "praticamente sì", "praticamente si",
    "direi di sì", "direi di si", "ma sì", "ma si",
    "eh sì", "eh si", "sì certo", "si certo",
    "sì ok", "si ok", "sì vai", "si vai",
    "mi pare di sì", "mi pare di si", "potrei dire di sì",
    "penso proprio", "grossomodo", "in linea di massima",
    "direi sì", "direi si", "certo che sì", "certo che si",
    "ma certo", "ovvio", "chiaramente", "eccome", "figurati",
    "certo certo", "ok certo", "ok vai", "ok andiamo",
    "sì andiamo", "si andiamo", "dai andiamo", "forza", "pronti",
    "ci sono", "son qui", "sono qui", "ci sto", "mi interessa",
    "voglio provare", "voglio farlo", "voglio iniziare",
    "partiamo", "iniziamo", "si parte", "facciamo", "proviamo",
    # Dopo spiegazione
    "d'accordo", "daccordo", "va bene così", "va bene cosi",
    "ok capito", "ho capito tutto", "tutto chiaro", "sì tutto chiaro",
    "si tutto chiaro", "capito tutto", "ok ho capito", "ah ok",
    "ah sì capito", "ah si capito", "ok dai", "ok procediamo",
    "procediamo", "andiamo avanti", "vai avanti", "continua",
    "ok continua", "sì continua", "si continua", "ok andiamo avanti",
    "ok procedi", "procedi", "sì procedi", "si procedi",
    "ok iniziamo", "sì iniziamo", "si iniziamo", "ok partiamo",
    "sì partiamo", "si partiamo", "ok dai andiamo",
    "interessante", "ok interessante", "mi sembra interessante",
    "sembra interessante", "ok sembra bello", "ok sembra buono",
    "ok ci sto", "ci sto", "ok sono dentro", "sono dentro",
    "ok sono interessato", "sono interessato", "ok mi interessa",
    "fantastico", "ottimo", "benissimo", "bene",
    "perfetto grazie", "ok grazie", "grazie capito",
    "ok grazie mille", "perfetto capito", "ok tutto chiaro",
    "sì tutto ok", "si tutto ok", "ok tutto ok",
    # App in passato
    "qualcuna", "qualcuno", "una o due", "un paio", "alcune",
    "ne ho fatta qualcuna", "ho fatto", "ne ho fatte",
    "ho già fatto", "già fatto", "già fatta",
    "ho esperienza", "ho già provato", "già provato",
    "ne ho fatta una", "ne ho fatte due", "ne ho fatte alcune",
    "ho già revolut", "ho già bbva", "ho già buddy",
    "ho già krak", "ho già isybank", "ho già credit agricole",
    "tipo revolut", "tipo bbva", "tipo buddy",
    "ho fatto revolut", "ho fatto bbva", "ho fatto buddy",
    "ho fatto isybank", "ho fatto krak", "ho fatto credit agricole",
    "revolut sì", "bbva sì", "buddy sì", "krak sì",
    "revolut si", "bbva si", "buddy si", "krak si",
    "ne conosco qualcuna", "ne ho già usata qualcuna",
    "già registrato", "già registrata", "ho già un profilo",
    "1", "2", "3", "4", "5", "6",
    "una", "due", "tre", "quattro", "cinque", "sei",
    "solo una", "solo due", "ne ho fatta solo una",
    "3 o 4", "2 o 3", "4 o 5", "un paio",
    "alcune sì", "qualcuna sì", "qualcuna si",
    "siuro", "siurissimo", "top", "👍", "✅", "💪", "🔥",
    # Numeri e quantità generiche
    "qualcosa", "qualcosa ho fatto", "ho fatto qualcosa",
    "roba simile", "ho fatto roba simile", "cose simili",
    "ho fatto cose simili", "già ci ho provato",
    "ho già avuto esperienze", "ho esperienza con le app",
    "conosco il meccanismo", "so come funziona",
    "forse qualcuna", "forse una", "forse due",
    "ne ho fatta qualcuna ma non ricordo",
    "qualcuna ma non so quale",
}

NEGATIVO = {
    "no", "nope", "nein", "nada", "niente", "nessuna",
    "nessuno", "mai", "nemmeno", "neanche", "neppure",
    "assolutamente no", "per niente", "proprio no",
    "no davvero", "no mai", "no nessuna", "no niente",
    "non ne ho fatta nessuna", "non ne ho fatta nemmeno una",
    "non le conosco", "non le ho mai fatte", "non ho mai fatto",
    "non ho mai usato", "non ho mai provato",
    "non sapevo nemmeno esistessero", "non ne sapevo niente",
    "non ne avevo mai sentito parlare",
    "zero", "nulla", "nessuna di queste", "nessuna purtroppo",
    "ancora nessuna", "ancora niente", "per ora nessuna",
    "non ancora", "nah", "na",
    "non ho fatto niente del genere",
    "non conosco nessuna di queste app",
    "niente di niente", "zero assoluto", "davvero nessuna",
    # Non conosce i bonus app
    "non lo so", "non so cosa sono", "non ne so niente",
    "non ne so nulla", "non so di cosa parli",
    "non so di cosa si tratta", "non ho idea",
    "non ho la minima idea", "non so",
    "nemmeno so cosa sono", "non sapevo",
    "non sapevo cosa fossero", "non conosco",
    "mai sentito", "mai sentite",
    "cosa sono", "non so cosa siano",
    "non ci capisco niente", "non capisco",
    "prima volta che sento", "prima volta",
    "non ho esperienza", "sono nuovo", "sono nuova",
    "parto da zero", "zero conoscenze",
    # Parzialmente negativo
    "non tanto", "non proprio", "più o meno no", "piu o meno no",
    "non del tutto", "non esattamente", "non direi",
    "mah dipende", "mah", "dipende cosa intendi",
    "dipende", "non saprei", "boh dipende",
    "non molto", "poco", "quasi no", "tendenzialmente no",
    "direi di no", "credo di no", "penso di no",
    "non credo", "non penso", "non mi sembra",
    "non mi pare", "forse no", "probabilmente no",
    "più no che sì", "più no che si",
}

VAGO = {
    "non ricordo", "non mi ricordo", "non ricordo bene",
    "non ricordo più", "quasi tutte", "tutte",
    "praticamente tutte", "tutte quante",
    "boh", "non saprei", "non lo so bene",
    "non sono sicuro", "non sono sicura",
    "mi sembra di aver fatto", "credo di aver fatto",
    "forse revolut", "forse bbva", "forse buddy",
    "forse isybank", "forse krak", "forse credit agricole",
    "mi sembra revolut", "credo revolut",
    "non ricordo il nome", "qualcuna ma non ricordo quale",
    "alcune ma non ricordo quali",
    "tipo una ma non ricordo", "forse una o due non ricordo",
    "non ricordo se ho completato", "non so se vale",
    "ne ho fatta una ma non so se conta",
    "ho aperto un conto ma non so se ho preso il bonus",
}

FRUSTRAZIONI = {
    "lascia perdere", "lascia stare", "non mi interessa più",
    "non interessa", "smettila", "vai via",
    "non voglio più", "ho cambiato idea",
    "non fa per me", "non è per me", "no grazie",
    "arrivederci", "ciao ciao", "bye", "goodbye",
    "non ho voglia", "non me ne frega", "non me ne frega niente",
    "non me ne frega nulla", "vaffanculo", "fanculo",
    "che palle", "rompiballe", "lasciami stare",
    "non ho tempo per queste cose", "non mi interessa",
    "ho cambiato idea grazie", "non voglio più saperne",
}

# ─── DOMANDE FUORI FLUSSO ────────────────────────────────────────
DOMANDE_NON_SO_PERCHE_QUI = {
    "non so perché sono qui", "non so come sono finito qui",
    "ho cliccato per sbaglio", "sono capitato qui per caso",
    "non so cosa faccio qui", "ho cliccato il link ma non so",
    "cosa è questo", "cos'è questo bot", "dove sono finito",
    "come funziona questo", "che cos'è questa chat",
    "non capisco dove sono", "mi sono perso",
    "ho cliccato senza capire", "non so cosa sia",
    "non so di cosa si tratta", "ma cosa è",
}

DOMANDE_CHI_SEI = {
    "chi sei", "cosa sei", "sei un bot", "sei un robot",
    "sei una persona", "sei umano", "sei reale", "sei vero",
    "sei automatico", "c'è qualcuno", "c'è una persona",
    "parla con me una persona", "risponde una persona",
    "sei intelligenza artificiale", "sei ia", "sei ai",
    "sei chatgpt", "sei un programma", "sei una macchina",
    "chi mi sta scrivendo", "chi risponde", "con chi parlo",
    "stai parlando tu", "sei luca", "sei luca puleo",
    "ma sei luca", "parli con me tu luca",
    "mi stai scrivendo tu", "sei una persona vera",
    "c'è qualcuno dall'altra parte", "dall'altra parte c'è qualcuno",
}

DOMANDE_PERCHE_BOT = {
    "perché devo parlare col bot", "perché non parlo con luca",
    "perché non mi contatta luca direttamente",
    "voglio parlare con luca", "dammi luca",
    "voglio luca", "passa luca", "metti luca",
    "non voglio parlare col bot", "preferisco parlare con una persona",
    "perché devo rispondere a un bot",
    "non mi piace parlare con i bot",
    "perché non mi scrivi tu luca",
    "vorrei parlare direttamente con lui",
    "posso parlare con luca",
}

DOMANDE_FUNZIONAMENTO = {
    "come funziona", "di cosa si tratta", "cos'è",
    "dimmi di più", "che cosa sono", "cosa sono i bonus",
    "come funzionano i bonus", "spiegami",
    "spiegami come funziona", "dimmi come funziona",
    "cosa sono le bonus app", "cosa sono questi bonus",
    "di cosa si tratta esattamente", "non ho capito di cosa si tratta",
    "non ho capito", "puoi spiegarmi meglio",
    "puoi spiegare meglio", "spiegami meglio",
    "non ho capito bene", "puoi ripetere",
    "cosa devo fare", "come si fa", "come funziona esattamente",
    "ma di cosa si tratta", "ma cos'è",
    "che cosa sono i bonus app", "cosa si fa con queste app",
    "non ho capito cosa sono i bonus app",
    "ma cosa sono questi bonus", "bonus di cosa",
    "che tipo di bonus sono", "come funzionano esattamente",
}

DOMANDE_GUADAGNO_TOTALE = {
    "ma cosa ci guadagno", "cosa ci guadagno", "cosa guadagno",
    "ma cosa guadagno", "cosa guadagno io", "ma cosa guadagno io",
    "cosa ci ricavo", "ma cosa ci ricavo", "cosa prendo",
    "ma cosa prendo", "cosa ottengo", "ma cosa ottengo",
    "cosa mi danno", "ma cosa mi danno", "cosa ricevo",
    "ma cosa ricevo", "quanto prendo", "quanto ottengo",
    "quanto ricevo", "quanto ci ricavo",
    "quanto si guadagna in totale", "quanto posso guadagnare in totale",
    "quanto si fa in totale", "quanti soldi si fanno",
    "quanto si guadagna", "quanto posso fare",
    "quanti euro si fanno", "quanto si incassa",
    "quanto posso guadagnare", "totale guadagno",
    "quanto guadagno se le faccio tutte",
    "se le faccio tutte quanto prendo",
    "quanto prendo in tutto", "quanto incasso in tutto",
    "quanti soldi posso fare", "quanto posso prendere",
    "cifra totale", "totale bonus", "somma totale",
    "quanto fa in tutto", "in totale quanto si prende",
}

DOMANDE_QUANTE_APP = {
    "quante app devo fare", "quante sono le app",
    "quante app ci sono", "quante app in totale",
    "quante applicazioni", "quante sono",
    "quant'è la lista", "quanto è lunga la lista",
    "quante ne devo fare", "quante applicazioni devo fare",
    "quante app sono", "numero di app",
}

DOMANDE_TEMPO = {
    "quanto tempo ci vuole", "quanto tempo ci vuole per app",
    "quanto ci metto", "quanto dura", "quanto tempo richiede",
    "quanto impiego", "quanto è lungo il processo",
    "quanto ci vuole", "in quanto tempo",
    "quanto tempo per ogni app", "quanto tempo per una app",
    "ci vuole molto", "è lungo", "è veloce",
    "si fa in fretta", "quanto è rapido",
    "quanto tempo mediamente", "in media quanto ci vuole",
}

DOMANDE_SOLO_SERA = {
    "posso farlo solo la sera", "ho tempo solo la sera",
    "lo faccio solo di sera", "solo la sera posso",
    "lavoro tutto il giorno", "sono disponibile solo la sera",
    "ho tempo libero solo la sera", "posso farlo nel weekend",
    "lo faccio nel fine settimana", "solo il weekend ho tempo",
    "posso farlo in qualsiasi momento",
    "quando voglio posso farlo",
    "devo farlo in un momento preciso",
    "c'è un orario preciso", "devo fare tutto in una volta",
    "posso dilazionarlo", "posso farlo a rate",
    "non ho molto tempo libero", "sono molto impegnato",
    "ho una vita", "ho impegni",
}

DOMANDE_VIRUS = {
    "ci sono virus", "non voglio virus", "è sicuro scaricare",
    "ha virus", "potrebbe avere virus", "è sicuro",
    "le app sono sicure", "sono app sicure",
    "non mi fido a scaricare", "scarico sicuro",
    "non voglio scaricare roba strana", "app strane",
    "da dove si scaricano", "dove si scaricano",
    "si trovano sull'app store", "si trovano sul play store",
    "sono su app store", "sono su play store",
    "dove le trovo", "come le scarico",
}

DOMANDE_REVOLUT_GIA_APERTO = {
    "ho già revolut", "ho già un conto revolut",
    "revolut ce l'ho già", "revolut l'ho già fatto",
    "ho già fatto revolut", "ce l'ho già revolut",
    "revolut l'ho già aperto", "ho già aperto revolut",
    "ma ho già revolut", "ho revolut da anni",
    "uso già revolut", "ho già bbva", "ho già un conto bbva",
    "bbva ce l'ho già", "ho già buddy", "ho già buddybank",
    "ho già isybank", "ho già krak", "ho già credit agricole",
    "ne ho già alcune aperte", "alcune le ho già aperte",
    "ne ho già alcune", "alcune ce le ho già",
}

DOMANDE_FATTO_TUTTE = {
    "le ho fatte tutte", "le ho già fatte tutte",
    "tutte le ho fatte", "le ho fatte tutte quante",
    "ho già tutte queste app", "le conosco tutte",
    "le ho già tutte", "ho già tutte",
    "le ho già fatte tutte quante",
    "sono in possesso di tutte",
    "ce le ho già tutte",
}

DOMANDE_BONUS_ARRIVA = {
    "i bonus arrivano davvero", "i soldi arrivano davvero",
    "mi pagano davvero", "è vero che pagano",
    "ma pagano davvero", "arrivano i soldi",
    "si ricevono davvero i bonus", "funziona davvero",
    "non è che non pagano", "e se non arrivano i soldi",
    "quando arrivano i bonus", "in quanto tempo arrivano",
    "quanto ci vuole per ricevere il bonus",
    "quando mi pagano", "quando ricevo i soldi",
    "i soldi quando arrivano", "tempi di pagamento",
}

DOMANDE_MINORENNE = {
    "sono minorenne", "ho meno di 18 anni", "non ho 18 anni",
    "ho 16 anni", "ho 17 anni", "ho 15 anni",
    "non sono maggiorenne", "sono under 18",
    "posso farlo da minorenne", "vale anche per i minorenni",
    "si può fare da minorenni", "funziona anche per minorenni",
    "mio figlio può farlo", "mia figlia può farlo",
    "mio fratello ha 16 anni", "mia sorella è minorenne",
}

DOMANDE_DOCUMENTO = {
    "non ho documento", "non ho il documento",
    "documento scaduto", "ho il documento scaduto",
    "non ho carta di identità", "ho solo la patente",
    "vale la patente", "posso usare la patente",
    "ho solo il passaporto", "vale il passaporto",
    "non ho tessera sanitaria", "ho perso la tessera",
    "serve proprio il documento", "quali documenti servono",
    "che documenti mi servono", "cosa serve per registrarsi",
    "cosa serve", "quali documenti",
}

DOMANDE_ESTERO = {
    "vivo all'estero", "sono all'estero", "abito all'estero",
    "non sono in italia", "sono fuori dall'italia",
    "sono in inghilterra", "sono in germania", "sono in spagna",
    "sono emigrato", "sono un italiano all'estero",
    "vivo fuori dall'italia", "mi trovo all'estero",
    "funziona anche dall'estero", "si può fare dall'estero",
    "vale anche per chi vive all'estero",
}

DOMANDE_COME_FA_SOLDI_LUCA = {
    "come fa soldi luca", "come guadagna luca",
    "luca come guadagna", "cosa ci guadagna luca",
    "perché luca mi aiuta", "cosa ci guadagna lui",
    "qual è il suo interesse", "perché dovrebbe aiutarmi",
    "cosa guadagna lui", "luca cosa prende",
    "come funziona per luca", "luca prende qualcosa",
    "lui cosa ci guadagna", "qual è il guadagno di luca",
}

DOMANDE_GRATIS = {
    "perché mi aiuti gratis", "perché è gratis",
    "è gratuito", "non costa niente", "costa qualcosa a me",
    "devo pagare qualcosa", "c'è qualche costo nascosto",
    "ci sono costi nascosti", "non mi sembra gratis",
    "troppo bello per essere vero", "sembra troppo bello",
    "ma davvero è gratis", "non ci credo che è gratis",
    "c'è qualche fregatura", "dov'è la fregatura",
    "qual è la fregatura", "cosa c'è sotto",
    "cosa nasconde", "cosa non mi stai dicendo",
    "non c'è niente di gratis in questo mondo",
}

DOMANDE_SOLDI_MIEI = {
    "devo mettere soldi miei", "ci vogliono soldi miei",
    "serve un investimento", "devo investire",
    "quanto devo investire", "quanto devo mettere",
    "ci vuole capitale", "serve capitale iniziale",
    "devo avere soldi sul conto", "ci vogliono soldi sul conto",
    "serve un deposito", "devo depositare",
    "ci vuole un deposito iniziale",
    "parte da zero davvero", "si inizia da zero",
    "non serve investire niente",
}

DOMANDE_POSSO_SMETTERE = {
    "posso smettere", "posso smettere quando voglio",
    "se voglio smettere", "posso fermarmi",
    "sono obbligato a continuare", "devo per forza continuare",
    "posso bloccarmi", "posso interrompere",
    "non sono obbligato vero", "nessun vincolo",
    "ci sono vincoli", "ci sono obblighi",
    "sono libero di smettere", "rimango bloccato",
    "resto bloccato se smetto",
}

DOMANDE_APP_RESTANO = {
    "queste app restano sul telefono", "devo tenerle installate",
    "posso disinstallarle", "le tengo per sempre",
    "devo tenere le app", "restano le app",
    "rimangono le app", "le app rimangono installate",
    "dopo posso toglierle", "dopo le elimino",
    "le posso cancellare", "quanto le tengo",
    "per quanto tempo le tengo",
}

DOMANDE_FREGATO_ONLINE = {
    "ho già provato robe online", "mi hanno già fregato online",
    "ho già avuto brutte esperienze", "mi hanno già truffato",
    "non mi fido delle cose online", "le cose online non funzionano",
    "ho già perso soldi online", "online si viene sempre truffati",
    "non ci credo più alle cose online",
    "ho già provato e non ha funzionato",
    "mi hanno già preso in giro",
    "queste cose non funzionano mai",
    "è come tutte le altre truffe online",
    "ho già visto robe del genere", "solita fregatura",
}

DOMANDE_RECENSIONI = {
    "posso vedere recensioni", "voglio vedere feedback",
    "ci sono recensioni", "hai recensioni",
    "dove vedo i feedback", "voglio prove",
    "mi fai vedere le prove", "hai prove",
    "testimonianze", "ci sono testimonianze",
    "qualcuno ha guadagnato davvero", "qualcuno lo ha già fatto",
    "altri lo hanno fatto", "esempi di persone che hanno guadagnato",
    "mi fai vedere qualcuno che ha guadagnato",
    "hai screenshot di guadagni", "screenshot di bonifici",
    "screenshot di guadagni reali",
}

DOMANDE_FISCALE = {
    "luca ha partita iva", "è tutto in regola fiscalmente",
    "è in regola", "paga le tasse", "è tutto legale fiscalmente",
    "ma fiscalmente", "si dichiarano questi soldi",
    "devo dichiarare i bonus", "si dichiarano i bonus",
    "sono tassabili i bonus", "devo pagare tasse sui bonus",
    "come funziona fiscalmente", "questione fiscale",
}

DOMANDE_DATI = {
    "non voglio dare i miei dati", "non mi fido a dare i dati",
    "che fine fanno i miei dati", "privacy",
    "che fai con i miei dati", "usi i miei dati",
    "vendi i miei dati", "i miei dati sono al sicuro",
    "chi vede i miei dati", "dati personali",
    "non voglio condividere dati personali",
    "le mie credenziali restano mie",
    "le password restano mie", "non voglio dare le password",
    "devo dare le mie credenziali", "devo dare la password",
}

DOMANDE_FURTO = {
    "e se mi rubano i soldi", "possono rubarmi i soldi",
    "rischio di perdere i soldi", "e se vanno a vuoto i soldi",
    "possono accedere al mio conto", "hanno accesso al mio conto",
    "possono svuotarmi il conto", "è sicuro per il mio conto",
    "il conto è al sicuro", "i miei soldi sono al sicuro",
    "rischio per il conto corrente", "rischio per il mio conto",
}

DOMANDE_CONTO_BLOCCATO = {
    "mi bloccano il conto", "il conto può essere bloccato",
    "rischio di avere il conto bloccato",
    "ho sentito che bloccano il conto",
    "dicono che queste app bloccano i conti",
    "il conto viene bloccato", "rischio blocco conto",
    "è rischioso per il conto",
}

DOMANDE_CONTO_IN_ROSSO = {
    "ho il conto in rosso", "sono in rosso",
    "non ho saldo sul conto", "il conto è scoperto",
    "ho debiti", "non ho disponibilità",
    "sono indebitato", "ho il fido",
    "il conto è quasi a zero", "ho pochissimi soldi",
}

DOMANDE_SISTEMA_OPERATIVO = {
    "funziona su iphone", "è per android", "è per ios",
    "solo android", "solo iphone", "anche per iphone",
    "anche per android", "iphone o android",
    "ho un iphone", "ho un android", "ho un samsung",
    "funziona su samsung", "è disponibile su ios",
    "è disponibile su android", "app store o play store",
    "si trova su app store", "si trova su play store",
}

DOMANDE_TELEFONO_VECCHIO = {
    "ho il telefono vecchio", "telefono datato",
    "telefono non aggiornato", "telefono vecchio modello",
    "non so se supporta le app", "phone vecchio",
    "ho un telefono di 10 anni", "ho un telefono di 5 anni",
    "il mio telefono è vecchio", "non so se è compatibile",
    "potrebbe non supportare", "non so se va",
}

DOMANDE_APP_GIA_FATTA_ANNI_FA = {
    "l'ho già fatta anni fa", "l'ho fatta tempo fa",
    "l'avevo già fatta", "anni fa l'avevo già fatta",
    "già fatta in passato", "fatta qualche anno fa",
    "l'ho fatta qualche anno fa", "la feci tempo fa",
    "ho già quel conto da anni", "ho quel conto da tempo",
    "ce l'ho già da prima", "l'avevo già aperta",
}

DOMANDE_SORELLA_AMICO = {
    "può farlo mia sorella", "può farlo mio fratello",
    "può farlo un mio amico", "posso farlo per qualcun altro",
    "può farlo mia moglie", "può farlo mio marito",
    "può farlo il mio ragazzo", "può farlo la mia ragazza",
    "può farlo mia madre", "può farlo mio padre",
    "possiamo farlo in famiglia", "lo possono fare anche i miei",
    "anche un mio familiare può farlo",
}

DOMANDE_CONTO_PADRE = {
    "posso farlo con il conto di mio padre",
    "posso usare il conto di un altro",
    "posso usare il conto di mia moglie",
    "posso usare il conto di qualcun altro",
    "conto intestato a qualcun altro",
    "farlo con un altro documento",
    "usare il documento di qualcun altro",
}

DOMANDE_LUCA_ITALIANO = {
    "luca è italiano", "luca parla italiano",
    "dove vive luca", "luca da dove è",
    "parla in italiano", "è un italiano",
    "di dove è luca", "luca è di dove",
}

DOMANDE_STRANIERO = {
    "sono straniero", "non sono italiano",
    "parlo poco italiano", "capisco poco italiano",
    "non capisco bene l'italiano", "sono di un altro paese",
    "non sono italiano ma posso farlo",
    "funziona anche per gli stranieri",
    "sono rumeno", "sono cinese", "sono marocchino",
    "vengo da un altro paese",
}

DOMANDE_QUANTO_GUADAGNA_LUCA = {
    "quanti soldi ha guadagnato luca",
    "quanto ha guadagnato luca", "luca quanto ha guadagnato",
    "quanto ha fatto luca", "i guadagni di luca",
    "luca guadagna tanto", "luca ha guadagnato tanto",
    "quanto ha incassato luca",
}

DOMANDE_SOCIAL_LUCA = {
    "luca ha un profilo social", "voglio verificare luca",
    "dove trovo luca sui social", "luca è sui social",
    "posso vedere il profilo di luca", "dove vedo luca",
    "link a luca", "profilo di luca", "instagram di luca",
    "tiktok di luca", "youtube di luca",
    "luca esiste davvero", "voglio vedere chi è luca",
    "mi mandi il profilo di luca", "dove lo trovo",
}

DOMANDE_CARTA_CREDITO = {
    "non ho la carta di credito", "ho solo il bancomat",
    "serve la carta di credito", "serve bancomat",
    "ho solo prepagata", "ho solo postepay",
    "ho solo contanti", "non ho carta",
    "ho una postepay", "ho un bancomat",
    "carta di debito va bene",
}

DOMANDE_QUANDO_CONTATTA = {
    "quando mi contatta luca", "quanto ci vuole per essere contattato",
    "quando mi scrivi", "quando mi chiami",
    "ho fretta", "mi serve veloce", "quando avviene il contatto",
    "in quanto tempo mi contatta", "quanto aspetto",
    "tempi di risposta", "quando risponde",
    "quando mi contatta", "ci vuole molto",
    "aspetto tanto", "aspetto poco",
    "luca mi contatta subito", "mi contatta oggi",
}

DOMANDE_SE_NON_RISPONDE = {
    "se luca non mi risponde", "e se non mi risponde",
    "cosa faccio se non risponde", "e se non risponde nessuno",
    "come lo contatto se non risponde",
    "e se mi ignora", "e se non si fa vivo",
    "non risponde mai nessuno", "tanto non risponde",
    "dubbio sulla risposta", "non risponde",
}

DOMANDE_ACCESSO_DATI_APP = {
    "queste app hanno accesso al mio conto",
    "le app accedono al conto", "le app vedono il conto",
    "queste app hanno accesso ai dati",
    "le app accedono ai dati", "le app vedono i dati",
    "hanno accesso al conto corrente principale",
    "vedono il conto corrente",
}

DOMANDE_PERCHE_CHIEDI_APP = {
    "perché mi chiedi delle app", "perché vuoi sapere le app",
    "a cosa serve sapere le app", "perché ti interessa",
    "cosa fai con questa informazione",
    "perché devo dirlo", "è necessario dirlo",
    "ha importanza", "perché lo chiedi",
}

DOMANDE_ISYBANK = {
    "cos'è isybank", "cosa è isybank", "isybank cos'è",
    "non conosco isybank", "non so cos'è isybank",
    "isybank non la conosco", "mai sentito isybank",
    "isybank di cosa è",
}

DOMANDE_N26_SATISPAY = {
    "ho fatto n26", "ho n26", "uso n26",
    "ho fatto satispay", "ho satispay", "uso satispay",
    "ho fatto hype", "ho hype", "uso hype",
    "ho fatto vivid", "ho vivid",
    "ho fatto bunq", "ho bunq",
    "ho fatto wise", "ho wise",
    "ho un conto che non è in lista",
    "ho fatto un'app che non c'è",
    "ho fatto altre app bancarie",
}


# ─── SINONIMI AGGIUNTIVI ─────────────────────────────────────────
AFFERMATIVO.update({
    # Conferme entusiaste
    "assolutamente sì", "assolutamente si", "certo che si", "ovvio che sì",
    "ovvio che si", "chiaramente sì", "chiaramente si", "senza dubbio sì",
    "senza dubbio si", "indubitabilmente", "indubbiamente",
    "certamente sì", "certamente si", "naturalmente sì", "naturalmente si",
    "ovviamente sì", "ovviamente si", "decisamente sì", "decisamente si",
    "assolutamente d'accordo", "pienamente d'accordo", "concordo",
    "confermo tutto", "sì confermo", "si confermo", "ok confermo",
    # Brevi e dirette
    "sì.", "si.", "ok.", "okay.", "certo.", "esatto.", "giusto.",
    "yep.", "yes.", "yeah.", "sure.", "dai.", "vai.", "d'accordo.",
    "sì sì", "si si", "già già", "ok ok ok", "si si si",
    "sì sì sì", "esatto esatto", "giusto giusto",
    # Slang e giovanile
    "sis", "yessir", "yass", "yep yep", "roger that", "affermativo",
    "10 e lode", "bravissimo", "benone", "ottimamente",
    "alla grande", "figurati", "ma certo che sì", "ma certo che si",
    "ma ovvio", "ma chiaro", "ma certo", "be' sì", "be' si",
    "eh già", "eh sì", "eh si", "beh sì", "beh si",
    # Con entusiasmo
    "fantastico", "meraviglioso", "ottimo", "benissimo", "perfettissimo",
    "grandioso", "magnifico", "splendido", "eccellente", "stupendo",
    "super", "bomba", "figo", "top notch", "esattamente sì",
    # Frasi complete affermative
    "sì lo so", "si lo so", "sì li conosco", "si li conosco",
    "sì ne so qualcosa", "si ne so qualcosa",
    "sì ho capito tutto", "si ho capito tutto",
    "sì sono pronto", "si sono pronto", "sì sono pronta", "si sono pronta",
    "sì sono interessato", "si sono interessato",
    "sì sono interessata", "si sono interessata",
    "sì voglio farlo", "si voglio farlo",
    "sì voglio saperne di più", "si voglio saperne di più",
    "sì dai andiamo", "si dai andiamo",
    "sì procediamo", "si procediamo",
    "sì cominciamo", "si cominciamo",
    "sì iniziamo pure", "si iniziamo pure",
    "ok dai procediamo", "ok dai iniziamo",
    "ok dai partiamo", "sì dai partiamo", "si dai partiamo",
    "ok dai continuiamo", "sì dai continuiamo", "si dai continuiamo",
    "sì andiamo avanti", "si andiamo avanti",
    "ok andiamo avanti", "sì vai avanti", "si vai avanti",
    "ok vai avanti", "procedi pure", "vai pure",
    "continua pure", "sì continua", "si continua",
    # App già fatte - esteso
    "ne ho fatte molte", "ne ho fatte parecchie", "ne ho fatte diverse",
    "ho già diversi conti", "ho già parecchi conti",
    "ho fatto diverse app bancarie", "ho molti conti aperti",
    "ho fatto roba simile in passato", "ho esperienze simili",
    "ho già esperienza con queste cose",
    "sì ne ho qualcuna", "si ne ho qualcuna",
    "sì alcune sì", "si alcune si",
    "alcune le ho già", "alcune ce le ho già",
    "qualcuna sì l'ho fatta", "qualcuna si l'ho fatta",
    "ne ho fatta più di una", "ne ho fatte più di una",
    "qualcuna di queste sì", "qualcuna di queste si",
    "ho fatto buddy", "ho fatto buddybank",
    "ho fatto credit", "ho credit agricole",
    "ho già krak", "ho già kraken", "krak sì", "krak si",
    "ho l'app di isybank", "ho isybank sul telefono",
})

NEGATIVO.update({
    # Negazioni forti
    "assolutamente no", "assolutamente niente", "assolutamente nessuna",
    "proprio no", "proprio niente", "proprio nessuna",
    "decisamente no", "categoricamente no", "certamente no",
    "di certo no", "per niente", "per nulla",
    "nemmeno per sogno", "manco per idea", "manco per niente",
    "neanche a parlarne", "nemmeno a parlarne",
    "non ne so nulla di nulla", "non ne so assolutamente niente",
    "non ho la minima idea di cosa siano",
    "non ho mai sentito parlare di queste cose",
    "è la prima volta che sento questa cosa",
    "non so di cosa stai parlando",
    "non capisco di cosa si tratta",
    "non ho idea di cosa siano",
    # Zero conoscenza
    "sono completamente all'oscuro", "non ne so niente di niente",
    "zero assoluto", "completamente a zero",
    "parto proprio da zero", "parto da zero assoluto",
    "non ho mai fatto niente del genere in vita mia",
    "non ho mai avuto a che fare con queste cose",
    "non ho assolutamente idea",
    "è la prima volta che ne sento parlare",
    "non sapevo nemmeno che esistessero queste cose",
    # Parzialmente negativo
    "non tanto", "non proprio", "non del tutto",
    "non esattamente", "non direi",
    "mah dipende cosa intendi", "mah dipende",
    "dipende cosa intendi", "non molto",
    "quasi no", "tendenzialmente no", "direi di no",
    "credo di no", "penso di no", "non credo",
    "non penso", "non mi sembra", "non mi pare",
    "forse no", "probabilmente no",
    "più no che sì", "più no che si",
    "non troppo", "non granché", "non granchè",
    "abbastanza poco", "pochissimo",
    "non ne so molto", "ne so pochissimo",
    "ne so poco", "ne so ben poco",
    "ho sentito qualcosa ma non so bene cosa sia",
    "ho sentito vagamente ma non so",
    "ho una vaga idea ma non so bene",
    # App non fatte
    "non ne ho fatta nemmeno una di quelle",
    "di quelle specifiche no", "di queste no",
    "non ho nessuna di quelle app",
    "non ho nessuna di queste app",
    "non le ho mai scaricate",
    "non le ho mai installate",
    "non ho mai aperto nessuno di quei conti",
    "non ho nessuno di quei conti",
})

FRUSTRAZIONI.update({
    "non me ne frega", "non me ne frega niente", "non me ne frega nulla",
    "vaffanculo", "fanculo", "che palle", "rompiballe",
    "lasciami stare", "non ho tempo per queste cose",
    "non mi interessa per niente", "non mi interessa affatto",
    "ho cambiato idea grazie", "non voglio più saperne",
    "non ne voglio sapere", "non ne voglio sapere niente",
    "non voglio continuare", "smetto qui", "mi fermo qui",
    "non rispondo più", "la smetto qui",
    "ho sbagliato a cliccare", "non mi interessa questa cosa",
    "non fa per me questa roba", "non è roba per me",
    "non vale la pena",
    "perdita di tempo", "è una perdita di tempo",
    "non ho voglia", "non ho la voglia",
    "non ho energia per queste cose",
})

DOMANDE_CHI_SEI.update({
    "ma chi sei", "ma cosa sei", "sei davvero un bot",
    "stai leggendo davvero", "mi legge davvero qualcuno",
    "c'è qualcuno in ascolto", "c'è qualcuno che legge",
    "sei un algoritmo", "sei automatizzato",
    "rispondi in automatico", "sei una risposta automatica",
    "questo è un bot automatico", "stai rispondendo da solo",
    "chi ha creato questo bot", "chi ti ha fatto",
    "sei fatto da luca", "luca ha fatto questo bot",
    "chi gestisce questo bot", "chi c'è dietro",
    "chi risponde qui", "non ci credo che sei un bot",
    "sembri una persona", "sembri umano",
    "scrivi troppo bene per essere un bot",
    "questo bot è intelligente", "bot intelligente",
})

DOMANDE_QUANDO_CONTATTA.update({
    "quando mi contatta luca di preciso", "entro quando mi contatta",
    "oggi mi contatta", "domani mi contatta",
    "mi contatta subito", "mi contatta presto",
    "quanto devo aspettare", "aspetto molto",
    "ci vuole tanto", "ci vuole poco",
    "è rapido a rispondere", "risponde velocemente",
    "risponde entro oggi", "risponde entro domani",
    "entro quanto tempo", "in poco tempo",
    "urgente", "ho urgenza", "è urgente per me",
    "mi serve prima possibile", "subito",
    "ho fretta di iniziare", "voglio iniziare subito",
    "posso iniziare oggi", "posso iniziare domani",
    "quando iniziamo", "quando si parte",
    "quando posso iniziare", "posso iniziare ora",
})

DOMANDE_SOLDI_MIEI.update({
    "ci vuole un minimo di soldi", "serve un minimo",
    "ci vogliono almeno x euro", "devo avere un minimo sul conto",
    "serve un saldo minimo", "ci vuole saldo",
    "devo caricare il conto", "devo versare qualcosa",
    "devo fare un versamento", "devo mettere qualcosa",
    "ci sono spese iniziali", "spese di attivazione",
    "costi di apertura", "devo pagare per aprire",
    "ci sono commissioni", "commissioni di apertura",
    "è tutto gratis davvero", "nessuna spesa nascosta",
    "sicuro che non ci sono costi", "garantisci che è gratis",
    "giuro che è gratis", "prometti che è gratis",
})

DOMANDE_MINORENNE.update({
    "non ho ancora 18 anni", "ho quasi 18 anni",
    "compio 18 anni tra poco", "sono giovane",
    "sono un ragazzo giovane", "sono una ragazza giovane",
    "ho ancora pochi anni", "sono molto giovane",
    "vale anche per i giovanissimi",
    "funziona anche per chi ha 16 anni",
    "funziona anche per chi ha 17 anni",
    "mio figlio ha 16 anni", "mia figlia ha 17 anni",
    "mio nipote è minorenne", "mia nipote è minorenne",
    "ho un fratello minore", "ho una sorella minore",
    "può farlo chi è under 18",
})

DOMANDE_ESTERO.update({
    "non sono in italia in questo momento",
    "sono temporaneamente all'estero",
    "sono in vacanza all'estero",
    "lavoro all'estero", "studio all'estero",
    "vivo all'estero da anni", "mi sono trasferito all'estero",
    "sono emigrato da qualche anno",
    "sono in uk", "sono in usa", "sono in canada",
    "sono in australia", "sono in svizzera",
    "sono in francia", "sono in spagna",
    "abito fuori dall'italia",
})

DOMANDE_RECENSIONI.update({
    "voglio vedere le prove prima", "prima voglio prove",
    "dimmi qualcuno che ha già guadagnato",
    "conosco qualcuno che l'ha fatto",
    "hai qualche referenza", "qualche referenza",
    "posso parlare con qualcuno che lo ha già fatto",
    "mi fai parlare con qualcuno che ha già guadagnato",
    "mi dai qualche contatto di chi l'ha fatto",
    "voglio parlare con altri tuoi clienti",
    "dove vedo i risultati", "risultati reali",
    "screenshot di guadagni", "foto di guadagni",
    "dimostrazione di guadagni", "prove di guadagno",
    "hai screenshot", "hai foto",
})

DOMANDE_DATI.update({
    "i miei dati dove vanno", "dove finiscono i miei dati",
    "chi ha accesso ai miei dati", "chi vede le mie info",
    "le mie informazioni sono protette",
    "rispetti la privacy", "gdpr", "trattamento dati",
    "posso sapere come usi i miei dati",
    "non voglio che condividi i miei dati",
    "i miei dati non li condividete vero",
    "le mie info sono al sicuro vero",
    "non devo dare documenti a luca vero",
    "non devo mandare foto del documento vero",
    "devo mandare la foto del documento",
    "devo mandare selfie con documento",
})

DOMANDE_FURTO.update({
    "e se mi svuotano il conto", "e se spariscono i soldi",
    "e se perdono i miei soldi", "rischio di perdere tutto",
    "posso perdere i soldi che ho", "e se va storta",
    "e se qualcosa va male", "rischi per il conto",
    "il conto è protetto", "i soldi sono garantiti",
    "non rischio di perdere soldi vero",
    "non ci sono rischi economici vero",
    "rischio economico zero", "zero rischi finanziari",
})

DOMANDE_GRATIS.update({
    "sembra troppo bello per essere vero",
    "queste cose non sono mai gratis",
    "in questo mondo niente è gratis",
    "non mi tornano i conti",
    "qualcosa non quadra", "c'è qualcosa che non mi convince",
    "mi sembra strano che sia gratis",
    "dove sta il trucco", "qual è il trucco",
    "cosa ci guadagnate voi", "come fate i soldi voi",
    "c'è qualcosa di nascosto",
    "non è possibile che sia tutto gratis",
    "ci deve essere qualcosa che non va",
    "non ci credo che è tutto gratis",
})

# ══════════════════════════════════════════════════════════════════
# FUNZIONI DI CLASSIFICAZIONE
# ══════════════════════════════════════════════════════════════════

def is_yes(text: str) -> bool:
    t = text.strip().lower()
    neg_forti = [
        "non lo so", "non so", "non ne so", "non capisco",
        "non ho idea", "non sapevo", "mai sentito", "prima volta",
        "parto da zero", "non conosco", "spiegami", "cosa sono",
        "non tanto", "non proprio", "mah dipende", "dipende",
        "non molto", "quasi no", "direi di no", "credo di no",
        "penso di no", "forse no", "probabilmente no",
    ]
    for neg in neg_forti:
        if neg in t:
            return False
    if t in AFFERMATIVO:
        return True
    for kw in AFFERMATIVO:
        if kw in t:
            return True
    for app in ["revolut", "bbva", "isybank", "buddybank", "buddy", "credit agricole", "agricole", "krak"]:
        if app in t:
            return True
    return False

def is_no(text: str) -> bool:
    t = text.strip().lower()
    if t in NEGATIVO:
        return True
    for kw in NEGATIVO:
        if kw in t:
            return True
    return False

def is_vague(text: str) -> bool:
    t = text.strip().lower()
    if t in VAGO:
        return True
    for kw in VAGO:
        if kw in t:
            return True
    return False

def check_set(text: str, s: set) -> bool:
    t = text.strip().lower()
    if t in s:
        return True
    for kw in s:
        if kw in t:
            return True
    return False


# ─── NUOVE CASISTICHE DA ROLEPLAY ────────────────────────────────

DOMANDE_DIFFIDENZA_ONLINE = {
    "ho già sentito questa storia", "l'ho già sentita questa storia",
    "mio cugino ci ha provato", "un mio amico ci ha provato",
    "conosco qualcuno che non ha guadagnato",
    "ci ho già provato e non ha funzionato",
    "ho già perso tempo con robe simili",
    "non ha funzionato con altri", "anche altri non hanno guadagnato",
    "sembra sempre la solita fregatura", "è la solita storia",
    "ho già visto queste cose", "sempre le stesse promesse",
    "non ci casco più", "mi hanno già fregato così",
    "già provato non funziona", "non funziona mai",
}

DOMANDE_EQUITA_LUCA = {
    "luca guadagna di più di me", "non mi sembra equo",
    "luca ci guadagna più di me", "mi sfrutta",
    "mi usa per fare soldi", "mi sta usando",
    "guadagna grazie a me", "ci guadagna lui",
    "non è giusto", "non è equo", "è una cosa giusta",
    "perché dovrei aiutarlo a guadagnare",
    "se guadagna grazie a me non è giusto",
    "quanto guadagna luca rispetto a me",
    "luca guadagna quanto me", "guadagnano uguale",
}

DOMANDE_PERCHE_AIUTA = {
    "perché perde tempo ad aiutarmi",
    "non gli conviene farlo da solo",
    "perché mi aiuta", "cosa ci guadagna ad aiutarmi",
    "perché dovrebbe aiutarmi", "qual è il suo motivo",
    "cosa lo spinge ad aiutarmi",
    "perché non lo fa da solo",
    "gli conviene aiutarmi",
}

DOMANDE_REDDITO_CITTADINANZA = {
    "ho il reddito di cittadinanza", "prendo il rdc",
    "ho la naspi", "prendo la naspi", "sono disoccupato",
    "prendo sussidi", "ho sussidi statali",
    "reddito di cittadinanza", "naspi", "sussidio",
    "assegno di disoccupazione", "indennità di disoccupazione",
    "ammortizzatori sociali", "cassa integrazione",
    "reddito di inclusione", "rei", "isee basso",
    "ho l'isee", "con l'isee", "in base all'isee",
    "rischio qualcosa con i bonus", "perdo i sussidi",
    "mi tolgono il sussidio", "incide sul sussidio",
    "influisce sul reddito di cittadinanza",
}

DOMANDE_FISCALI_AVANZATE = {
    "questi bonus vengono considerati reddito",
    "devo dichiararli", "ai fini fiscali",
    "devo fare la dichiarazione dei redditi",
    "sono tassabili", "ci pagano le tasse",
    "vanno dichiarati", "fiscalmente come funziona",
    "commercialista", "dottore commercialista",
    "agenzia delle entrate", "fisco", "irpef",
    "modello 730", "modello unico", "dichiarazione fiscale",
}

DOMANDE_RESPONSABILITA = {
    "chi mi rimborsa", "chi paga se va male",
    "se perdo qualcosa chi risponde",
    "luca si prende la responsabilità",
    "c'è una garanzia", "garanzia di guadagno",
    "e se luca sbaglia", "e se mi dice una cosa sbagliata",
    "chi risponde dei danni", "responsabilità",
}

DOMANDE_SPALMARE_TEMPO = {
    "posso farlo su più giorni", "posso spalmarlo",
    "devo farlo tutto in un giorno",
    "posso farlo in più riprese", "posso farlo a tappe",
    "posso farlo poco alla volta", "posso farlo gradualmente",
    "devo farlo tutto di fila", "devo farlo in una volta",
    "posso iniziarne una e poi continuare dopo",
    "posso fare una app oggi e una domani",
}

DOMANDE_MODALITA_ASSISTENZA = {
    "come mi spiega luca", "luca come mi assiste",
    "come avviene l'assistenza", "come mi aiuta luca",
    "in chiamata", "in videochiamata", "per messaggio",
    "via chat", "via whatsapp", "via telegram",
    "vocale o scritto", "come comunichiamo",
    "parla in videochiamata", "fa videochiamate",
    "fa chiamate", "risponde in chat",
    "vocali", "messaggi vocali",
}

DOMANDE_PERSONE_ANZIANE = {
    "ho tanti anni", "sono anziano", "sono anziana",
    "ho 60 anni", "ho 65 anni", "ho 70 anni", "ho 72 anni",
    "ho 75 anni", "ho 80 anni", "sono in pensione",
    "sono pensionato", "sono pensionata",
    "non sono giovane", "sono vecchio", "sono vecchia",
    "non sono abituato alla tecnologia",
    "la tecnologia non fa per me",
    "non uso molto il telefono",
    "uso poco lo smartphone",
}

DOMANDE_LIMITE_DOMANDE = {
    "posso fare quante domande voglio",
    "c'è un limite alle domande",
    "posso chiedere sempre",
    "posso chiedere quante volte voglio",
    "posso ricontattarlo se non capisco",
    "posso scrivergli più volte",
    "se non capisco posso riscrivere",
    "posso chiedere aiuto ogni volta",
}

DOMANDE_COMPUTER = {
    "posso farlo dal computer", "si può fare dal pc",
    "funziona su computer", "funziona su pc",
    "ho il telefono rotto", "non ho il telefono",
    "ho solo il computer", "ho solo il pc",
    "ho solo il tablet", "posso usare il tablet",
    "si può fare da tablet", "funziona su tablet",
    "posso usare il laptop", "funziona su laptop",
}

DOMANDE_CHIUSURA_APP = {
    "se chiudo l'app prendo il bonus",
    "posso chiuderla subito dopo",
    "devo tenerla aperta", "devo usarla",
    "devo fare transazioni", "devo usare il conto",
    "devo tenere i soldi dentro", "devo lasciare soldi",
    "posso aprirla e chiuderla subito",
    "è sufficiente aprire il conto",
}

DOMANDE_RIAPERTURA_APP = {
    "posso riaprire un account che ho già chiuso",
    "ho chiuso il conto posso riaprirlo",
    "ho cancellato l'app posso rifarla",
    "avevo già revolut ma l'ho chiusa",
    "avevo già bbva ma l'ho chiusa",
    "ho già avuto quel conto in passato",
    "l'ho già avuta ma l'ho cancellata",
    "conto chiuso posso riaprire",
}

DOMANDE_DOCUMENTI_ALTRI = {
    "posso usare il documento di mia moglie",
    "posso usare i dati di qualcun altro",
    "posso registrarmi con i dati di mio marito",
    "usando il numero di telefono di un altro",
    "con il telefono di mia moglie",
    "con i dati di mio fratello",
    "posso fare più registrazioni con dati diversi",
    "posso usare più identità",
}

DOMANDE_SORDO_DISABILE = {
    "sono sordo", "sono sorda", "sono non udente",
    "ho problemi di udito", "non sento bene",
    "sono disabile", "ho una disabilità",
    "ho problemi fisici", "sono ipovedente",
    "non vedo bene", "ho problemi di vista",
}

DOMANDE_DOMANDE_PERSONALI_LUCA = {
    "luca è single", "luca ha una fidanzata",
    "luca è fidanzato", "luca è sposato",
    "quanti anni ha luca", "dove vive luca",
    "luca è bello", "com'è luca",
    "posso conoscere luca", "posso vederlo",
    "posso parlargli adesso",
}

def check_obiezione(text: str):
    if check_set(text, FRUSTRAZIONI): return "frustrazione"
    if check_set(text, DOMANDE_NON_SO_PERCHE_QUI): return "non_so_perche_qui"
    if check_set(text, DOMANDE_CHI_SEI): return "chi_sei"
    if check_set(text, DOMANDE_PERCHE_BOT): return "perche_bot"
    if check_set(text, DOMANDE_FUNZIONAMENTO): return "funzionamento"
    if check_set(text, DOMANDE_GUADAGNO_TOTALE): return "guadagno_totale"
    if check_set(text, DOMANDE_QUANTE_APP): return "quante_app"
    if check_set(text, DOMANDE_TEMPO): return "tempo"
    if check_set(text, DOMANDE_SOLO_SERA): return "solo_sera"
    if check_set(text, DOMANDE_VIRUS): return "virus"
    if check_set(text, DOMANDE_REVOLUT_GIA_APERTO): return "app_gia_aperta"
    if check_set(text, DOMANDE_FATTO_TUTTE): return "fatto_tutte"
    if check_set(text, DOMANDE_BONUS_ARRIVA): return "bonus_arriva"
    if check_set(text, DOMANDE_MINORENNE): return "minorenne"
    if check_set(text, DOMANDE_DOCUMENTO): return "documento"
    if check_set(text, DOMANDE_ESTERO): return "estero"
    if check_set(text, DOMANDE_COME_FA_SOLDI_LUCA): return "come_fa_soldi_luca"
    if check_set(text, DOMANDE_GRATIS): return "gratis"
    if check_set(text, DOMANDE_SOLDI_MIEI): return "soldi_miei"
    if check_set(text, DOMANDE_POSSO_SMETTERE): return "posso_smettere"
    if check_set(text, DOMANDE_APP_RESTANO): return "app_restano"
    if check_set(text, DOMANDE_FREGATO_ONLINE): return "fregato_online"
    if check_set(text, DOMANDE_RECENSIONI): return "recensioni"
    if check_set(text, DOMANDE_FISCALE): return "fiscale"
    if check_set(text, DOMANDE_DATI): return "dati"
    if check_set(text, DOMANDE_FURTO): return "furto"
    if check_set(text, DOMANDE_CONTO_BLOCCATO): return "conto_bloccato"
    if check_set(text, DOMANDE_CONTO_IN_ROSSO): return "conto_in_rosso"
    if check_set(text, DOMANDE_SISTEMA_OPERATIVO): return "sistema_operativo"
    if check_set(text, DOMANDE_TELEFONO_VECCHIO): return "telefono_vecchio"
    if check_set(text, DOMANDE_APP_GIA_FATTA_ANNI_FA): return "app_gia_fatta_anni_fa"
    if check_set(text, DOMANDE_SORELLA_AMICO): return "sorella_amico"
    if check_set(text, DOMANDE_CONTO_PADRE): return "conto_padre"
    if check_set(text, DOMANDE_LUCA_ITALIANO): return "luca_italiano"
    if check_set(text, DOMANDE_STRANIERO): return "straniero"
    if check_set(text, DOMANDE_QUANTO_GUADAGNA_LUCA): return "quanto_guadagna_luca"
    if check_set(text, DOMANDE_SOCIAL_LUCA): return "social_luca"
    if check_set(text, DOMANDE_CARTA_CREDITO): return "carta_credito"
    if check_set(text, DOMANDE_QUANDO_CONTATTA): return "quando_contatta"
    if check_set(text, DOMANDE_SE_NON_RISPONDE): return "se_non_risponde"
    if check_set(text, DOMANDE_ACCESSO_DATI_APP): return "accesso_dati_app"
    if check_set(text, DOMANDE_PERCHE_CHIEDI_APP): return "perche_chiedi_app"
    if check_set(text, DOMANDE_ISYBANK): return "isybank"
    if check_set(text, DOMANDE_N26_SATISPAY): return "n26_satispay"
    if check_set(text, DOMANDE_DIFFIDENZA_ONLINE): return "diffidenza_online"
    if check_set(text, DOMANDE_EQUITA_LUCA): return "equita_luca"
    if check_set(text, DOMANDE_PERCHE_AIUTA): return "perche_aiuta"
    if check_set(text, DOMANDE_REDDITO_CITTADINANZA): return "reddito_cittadinanza"
    if check_set(text, DOMANDE_FISCALI_AVANZATE): return "fiscali_avanzate"
    if check_set(text, DOMANDE_RESPONSABILITA): return "responsabilita"
    if check_set(text, DOMANDE_SPALMARE_TEMPO): return "spalmare_tempo"
    if check_set(text, DOMANDE_MODALITA_ASSISTENZA): return "modalita_assistenza"
    if check_set(text, DOMANDE_PERSONE_ANZIANE): return "persone_anziane"
    if check_set(text, DOMANDE_LIMITE_DOMANDE): return "limite_domande"
    if check_set(text, DOMANDE_COMPUTER): return "computer"
    if check_set(text, DOMANDE_CHIUSURA_APP): return "chiusura_app"
    if check_set(text, DOMANDE_RIAPERTURA_APP): return "riapertura_app"
    if check_set(text, DOMANDE_DOCUMENTI_ALTRI): return "documenti_altri"
    if check_set(text, DOMANDE_SORDO_DISABILE): return "sordo_disabile"
    if check_set(text, DOMANDE_DOMANDE_PERSONALI_LUCA): return "domande_personali_luca"
    return None

def calcola_punteggio(state: dict) -> tuple:
    punti = 0
    if state.get("conosce_bonus"): punti += 3
    if state.get("ha_fatto_app"): punti += 3
    app_fatte = state.get("app_fatte", [])
    if app_fatte and app_fatte != ["NON RICORDA / INCERTO"]:
        punti += min(len(app_fatte), 3)
    if state.get("fallback_count", 0) == 0: punti += 1
    if punti >= 7: return punti, "🔥 HOT"
    elif punti >= 4: return punti, "🟡 WARM"
    else: return punti, "🔵 COLD"

def get_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "state" not in context.user_data:
        context.user_data["state"] = {}
    return context.user_data["state"]

def get_current_question(state: dict) -> str:
    step = state.get("step")
    if step in ("conosce_bonus", "dopo_spiegazione", "dopo_spiegazione_attesa"):
        return "Sai come funzionano i bonus app?"
    elif step == "ha_fatto_app":
        return "Hai già fatto qualche app in passato?"
    elif step == "quali_app":
        return "Hai già fatto qualcuna di queste app?"
    elif step == "messaggio_finale":
        return "C'è qualcosa che vorresti far sapere a Luca prima di iniziare?"
    return ""

async def typing(update: Update, seconds: float = 1.3):
    await update.message.chat.send_action("typing")
    await asyncio.sleep(seconds)

async def send_lista_app(update: Update):
    await update.message.reply_text(LISTA_APP, parse_mode="MarkdownV2")

async def send_report(context, state: dict, user_obj, tipo: str = "normale"):
    app_fatte = state.get("app_fatte", [])
    fatte_str = ", ".join(app_fatte) if app_fatte else "Nessuna"

    if hasattr(user_obj, 'username') and user_obj.username:
        contatto = f"👤 @{user_obj.username} — [Contatta](https://t.me/{user_obj.username})"
    else:
        contatto = f"👤 Nome: {state.get('nome')} — Nessun username (ID: {getattr(user_obj, 'id', '?')})"

    punteggio, categoria = calcola_punteggio(state)
    intestazione = "🔔 NUOVO LEAD QUALIFICATO" if tipo == "normale" else "🟠 NUOVO LEAD DA CONTATTARE"

    report = (
        f"{intestazione}\n\n"
        f"{contatto}\n"
        f"──────────────\n"
        f"*Sapeva cos'erano i bonus app?* _\"{state.get('conosce_bonus_risposta', '—')}\"_\n"
        f"-\n"
        f"*Aveva già fatto app in passato?* _\"{state.get('ha_fatto_app_risposta', '—')}\"_\n"
        f"-\n"
        f"*App già fatte:* _\"{state.get('quali_app_risposta', '—')}\"_\n"
        f"──────────────\n\n"
        f"💬 Messaggio preparazione: _\"{state.get('messaggio_preparazione', '—')}\"_\n\n"
        f"📊 Punteggio: *{punteggio}/10* — {categoria}"
    )

    entry = {"report": report, "tipo": tipo, "time": datetime.now(IT_TZ)}
    if tipo == "normale":
        all_leads.append(entry)
    else:
        orange_leads.append(entry)

    try:
        await context.bot.send_message(chat_id=LUCA_CHAT_ID, text=report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Errore invio report: {e}")

async def followup_4h(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    state_ref = data["state_ref"]
    nome = data["nome"]
    if state_ref.get("step") in ("fine", None): return
    last = state_ref.get("last_message_time")
    if last and (datetime.now(IT_TZ) - last).total_seconds() < 4 * 3600 - 60: return
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(1.3)
        await context.bot.send_message(chat_id=chat_id, text=f"Ciao {nome}, sei ancora lì? Luca ti aspetta 👀")
    except Exception as e:
        logger.error(f"Errore follow-up 4h: {e}")

async def report_24h(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    state_ref = data["state_ref"]
    user_obj = data["user_obj"]
    if state_ref.get("step") == "fine": return
    last = state_ref.get("last_message_time")
    if last and (datetime.now(IT_TZ) - last).total_seconds() < 24 * 3600 - 60: return
    await send_report(context, state_ref, user_obj, tipo="arancione")

# ══════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or user.username or "amico"
    state = get_state(context)

    state.clear()
    state["step"] = "conosce_bonus"
    state["nome"] = first_name
    state["username"] = f"@{user.username}" if user.username else f"ID:{user.id}"
    state["link"] = f"t.me/{user.username}" if user.username else f"ID:{user.id}"
    state["fallback_count"] = 0
    state["last_message_time"] = datetime.now(IT_TZ)
    global_states[user_id] = state

    job_data = {"chat_id": user_id, "user_id": user_id, "nome": first_name, "state_ref": state, "user_obj": user}
    for job in context.job_queue.get_jobs_by_name(f"followup_{user_id}"):
        job.schedule_removal()
    for job in context.job_queue.get_jobs_by_name(f"report24_{user_id}"):
        job.schedule_removal()
    context.job_queue.run_once(followup_4h, 4 * 3600, data=job_data, name=f"followup_{user_id}")
    context.job_queue.run_once(report_24h, 24 * 3600, data=job_data, name=f"report24_{user_id}")

    try:
        ora = datetime.now(IT_TZ).strftime("%d/%m/%Y alle %H:%M")
        username_display = f"@{user.username}" if user.username else f"ID:{user.id}"
        await context.bot.send_message(
            chat_id=LUCA_CHAT_ID,
            text=f"👋 NUOVO LEAD ENTRATO\n\n👤 {first_name} ({username_display})\n🕐 {ora}"
        )
    except Exception as e:
        logger.error(f"Errore notifica start: {e}")

    await typing(update)
    await update.message.reply_text(
        f"Ciao {first_name}! 👋 Sono l'assistente personale di Luca Puleo — lui mi ha messo qui per conoscerti un po' prima di contattarti direttamente.\n\n"
        f"Ti faccio solo 3 domande veloci, ci vorrà meno di 2 minuti ⚡\n"
        f"Luca legge tutto quello che scrivi qui e ti contatterà in persona non appena avrò passato le tue info.\n\n"
        f"Partiamo: sai come funzionano i bonus app?"
    )

# ══════════════════════════════════════════════════════════════════
# COMANDI
# ══════════════════════════════════════════════════════════════════
async def riprendi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(LUCA_CHAT_ID): return
    args = context.args
    if not args:
        await update.message.reply_text("Usi:\n/riprendi [user_id] → manda report e aggiorna foglio\n/riprendi [user_id] \"testo\" → manda testo al lead e continua flusso")
        return
    try:
        target_id = int(args[0])
        paused_leads.discard(target_id)
        state = global_states.get(target_id, {})
        if len(args) == 1:
            if state:
                class FakeUser:
                    id = target_id
                    username = state.get("username", "").replace("@", "") or None
                    first_name = state.get("nome", "")
                    last_name = ""
                await send_report(context, state, FakeUser(), tipo="normale")
                append_lead_to_sheet(state.get("nome", ""), state.get("username", f"ID:{target_id}"), state.get("link", f"ID:{target_id}"))
                state["step"] = "fine"
                await context.bot.send_message(chat_id=target_id, text="Grazie per la pazienza! Luca ti contatterà a breve 🙌")
                await update.message.reply_text(f"✅ Report inviato e foglio aggiornato per ID {target_id}")
            else:
                await update.message.reply_text(f"⚠️ Nessuno stato trovato per ID {target_id}")
        else:
            testo = " ".join(args[1:]).strip('"').strip("'")
            await context.bot.send_message(chat_id=target_id, text=testo)
            await update.message.reply_text(f"✅ Inviato a {target_id}: \"{testo}\"")
    except Exception as e:
        await update.message.reply_text(f"Errore: {e}")

async def rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(LUCA_CHAT_ID): return
    cutoff = datetime.now(IT_TZ) - timedelta(hours=24)
    leads_24h = [l for l in all_leads if l["time"] >= cutoff]
    if not leads_24h:
        await update.message.reply_text("Nessun lead completato nelle ultime 24h.")
        return
    testo = f"📋 LEAD ULTIME 24H ({len(leads_24h)} totali)\n\n"
    testo += "\n\n──────────────\n\n".join([l["report"] for l in leads_24h])
    for i in range(0, len(testo), 4000):
        await update.message.reply_text(testo[i:i+4000], parse_mode="Markdown")

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(LUCA_CHAT_ID): return
    cutoff = datetime.now(IT_TZ) - timedelta(hours=24)
    leads_24h = [l for l in orange_leads if l["time"] >= cutoff]
    if not leads_24h:
        await update.message.reply_text("Nessun lead 🟠 nelle ultime 24h.")
        return
    testo = f"🟠 LEAD DA CONTATTARE ({len(leads_24h)} totali)\n\n"
    testo += "\n\n──────────────\n\n".join([l["report"] for l in leads_24h])
    for i in range(0, len(testo), 4000):
        await update.message.reply_text(testo[i:i+4000], parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════
# PROCESS MESSAGE
# ══════════════════════════════════════════════════════════════════
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    user = update.effective_user
    user_id = user.id
    state = get_state(context)
    step = state.get("step")
    nome = state.get("nome", "")

    state["last_message_time"] = datetime.now(IT_TZ)

    if user_id in paused_leads:
        return

    if not step:
        await start(update, context)
        return

    if step == "fine":
        return

    obiezione = check_obiezione(text)
    domanda_corrente = get_current_question(state)

    # ── OBIEZIONI ────────────────────────────────────────────────
    if obiezione == "frustrazione":
        await typing(update)
        await update.message.reply_text(f"Capito {nome}, se cambi idea sono qui 🙌")
        state["step"] = "fine"
        try:
            await context.bot.send_message(chat_id=LUCA_CHAT_ID, text=f"🔴 LEAD PERSO\n\n👤 {nome} (@{user.username or user_id})\nUltimo messaggio: \"{text}\"")
        except: pass
        return

    if obiezione == "non_so_perche_qui":
        await typing(update)
        await update.message.reply_text(
            f"Ciao {nome}! 👋 Ok, non ti preoccupare, ti spiego tutto. Sei qui perché hai cliccato il tasto nella pagina di Luca sui bonus app. "
            f"Sono l'assistente personale di Luca Puleo — lui mi ha messo qui per conoscerti un po' prima di contattarti direttamente. "
            f"Ti faccio solo 3 domande veloci, ci vorrà meno di 2 minuti ⚡\n\n{domanda_corrente}"
        )
        return

    if obiezione == "chi_sei":
        await typing(update)
        await update.message.reply_text(f"Sono l'assistente personale di Luca Puleo — lui mi ha messo qui per conoscerti un po' prima di contattarti direttamente. Ti faccio solo 3 domande veloci, ci vorrà meno di 2 minuti ⚡\n\n{domanda_corrente}")
        return

    if obiezione == "perche_bot":
        await typing(update)
        await update.message.reply_text(f"Luca è molto impegnato e gestisce tante persone contemporaneamente. Lui mi ha messo qui per conoscerti un po' prima di contattarti direttamente. Ti faccio solo 3 domande veloci, ci vorrà meno di 2 minuti ⚡ Luca legge tutto quello che scrivi qui e ti contatterà in persona non appena avrò passato le tue info.\n\n{domanda_corrente}")
        return

    if obiezione == "funzionamento":
        await typing(update)
        await update.message.reply_text(
            "Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri e fai dei semplici passaggi insieme a me, "
            "ci riconoscono dei bonus (soldi o buoni amazon) che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, "
            f"non è richiesto alcun deposito o spesa, ti dirò quali app usare e cosa fare. Se ci sei iniziamo.\n\n{domanda_corrente}"
        )
        return

    if obiezione == "guadagno_totale":
        await typing(update)
        await update.message.reply_text(f"Dipende dalle app attive al momento, in media +150€ 💰\n\n{domanda_corrente}")
        return

    if obiezione == "quante_app":
        await typing(update)
        await update.message.reply_text("Ok! Ti mando la lista delle app disponibili.")
        await update.message.chat.send_action("typing")
        await asyncio.sleep(1.3)
        await send_lista_app(update)
        return

    if obiezione == "tempo":
        await typing(update)
        await update.message.reply_text(f"Mediamente 5–10 minuti per applicazione. Puoi completarle tutte in poco tempo e ricevere i bonus nei tempi indicati dall'app 🕐\n\n{domanda_corrente}")
        return

    if obiezione == "solo_sera":
        await typing(update)
        await update.message.reply_text(f"Non è assolutamente un problema! Dopo che avrai risposto a tutte le mie domande, invierò a Luca tutte le tue risposte — ti organizzerai direttamente con lui per l'orario 🤝\n\n{domanda_corrente}")
        return

    if obiezione == "virus":
        await typing(update)
        await update.message.reply_text(f"Sì, le scarichi sul telefono da App Store o Google Play Store — niente virus. Sono app bancarie ufficiali! Ma non scaricarle adesso, per sbloccare i bonus devi seguire tutti i passaggi di Luca 📱\n\n{domanda_corrente}")
        return

    if obiezione == "app_gia_aperta":
        await typing(update)
        await update.message.reply_text(f"Non è un problema! In questo caso però non potrai sbloccare quel bonus, perché è un'app che hai già. Otterrai i bonus delle app restanti 💰\n\n{domanda_corrente}")
        return

    if obiezione == "fatto_tutte":
        await typing(update)
        await update.message.reply_text("Ok! Parlerai con Luca su come procedere. Intanto ti mando la lista delle app disponibili.")
        await update.message.chat.send_action("typing")
        await asyncio.sleep(1.3)
        await send_lista_app(update)
        return

    if obiezione == "bonus_arriva":
        await typing(update)
        await update.message.reply_text(f"Sì! Le app erogano bonus di benvenuto per incentivare le registrazioni. I bonus vengono accreditati direttamente sull'app che hai aperto — ognuna ha i suoi tempi, solitamente pochi giorni. Una volta ricevuti, Luca ti spiega come trasferirli sul tuo conto bancario principale 💸\n\n{domanda_corrente}")
        return

    if obiezione == "minorenne":
        await typing(update)
        await update.message.reply_text(f"Purtroppo no, i bonus app sono solo per i maggiorenni. Puoi effettuare le registrazioni con i documenti di qualcun altro (maggiorenne), ma ricorda che devi avere il suo CONSENSO!\n\n{domanda_corrente}")
        return

    if obiezione == "documento":
        await typing(update)
        await update.message.reply_text(f"Serve un documento di identità valido (carta di identità + tessera sanitaria) ed essere maggiorenni.\n\n{domanda_corrente}")
        return

    if obiezione == "estero":
        await typing(update)
        await update.message.reply_text(f"Se sei italiano/a e vivi all'estero, potrai sbloccare solo determinati bonus. Ne parlerai meglio con Luca.\n\n{domanda_corrente}")
        return

    if obiezione == "come_fa_soldi_luca":
        await typing(update)
        await update.message.reply_text(f"Le app pagano i bonus sia a te che a Luca. Per questo è nel suo interesse farti sbloccare e guadagnare più soldi possibili!\n\n{domanda_corrente}")
        return

    if obiezione == "gratis":
        await typing(update)
        await update.message.reply_text(f"Nessuna fregatura {nome}! Sono l'assistente personale di Luca Puleo. Le app pagano i bonus sia a te che a Luca — per questo è nel suo interesse aiutarti a guadagnare il più possibile 💪\n\n{domanda_corrente}")
        return

    if obiezione == "soldi_miei":
        await typing(update)
        await update.message.reply_text(f"Assolutamente no! Non è richiesto un investimento, si inizia da 0. Sono app gratuite. È richiesto solo essere maggiorenni e avere un documento di identità valido.\n\n{domanda_corrente}")
        return

    if obiezione == "posso_smettere":
        await typing(update)
        await update.message.reply_text(f"Assolutamente sì, puoi smettere di fare i bonus quando vuoi — nessun vincolo!\n\n{domanda_corrente}")
        return

    if obiezione == "app_restano":
        await typing(update)
        await update.message.reply_text(f"Le app restano sul telefono finché arriva il bonus, poi se vuoi puoi disinstallarle. Ne parlerai meglio con Luca 👍🏻\n\n{domanda_corrente}")
        return

    if obiezione == "fregato_online":
        await typing(update)
        await update.message.reply_text(f"Mi dispiace che tu abbia avuto brutte esperienze. Luca lavora in maniera diversa e con etica — c'è un motivo se sono +2 anni che aiuta e fa guadagnare le persone, con feedback sempre eccellenti.\n\n{domanda_corrente}")
        return

    if obiezione == "recensioni":
        await typing(update)
        await update.message.reply_text(
            "Certo che puoi! Per vedere i feedback entra nel suo canale [TELEGRAM](https://t.me/+ZU36p4Mf0QFmMTU0) o seguilo su [INSTAGRAM](https://www.instagram.com/lucapuleo.bsn/)",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        await asyncio.sleep(1.0)
        await update.message.reply_text(domanda_corrente)
        return

    if obiezione == "fiscale":
        await typing(update)
        await update.message.reply_text(f"Non posso fornire queste informazioni 🫱🏻‍🫲🏻\n\n{domanda_corrente}")
        return

    if obiezione == "dati":
        await typing(update)
        await update.message.reply_text(f"Non devi dare i tuoi dati personali a Luca — la registrazione la fai tu, le credenziali restano in mano a te!\n\n{domanda_corrente}")
        return

    if obiezione == "furto":
        await typing(update)
        await update.message.reply_text(f"Non possono rubarti i soldi — non è mai successo. Sono app bancarie ufficiali e verificate!\n\n{domanda_corrente}")
        return

    if obiezione == "accesso_dati_app":
        await typing(update)
        await update.message.reply_text(f"No, queste app non hanno accesso al tuo conto corrente principale.\n\n{domanda_corrente}")
        return

    if obiezione == "conto_bloccato":
        await typing(update)
        await update.message.reply_text(f"Dipende da vari fattori — se segui tutti i passaggi che ti dirà Luca e non infranga le regole delle app, non succede!\n\n{domanda_corrente}")
        return

    if obiezione == "conto_in_rosso":
        await typing(update)
        await update.message.reply_text(f"Valuterai direttamente con Luca per questo tipo di condizioni.\n\n{domanda_corrente}")
        return

    if obiezione == "sistema_operativo":
        await typing(update)
        await update.message.reply_text(f"Funziona sia su iPhone che su Android 📱\n\n{domanda_corrente}")
        return

    if obiezione == "telefono_vecchio":
        await typing(update)
        await update.message.reply_text(f"Verificherai direttamente con Luca la compatibilità.\n\n{domanda_corrente}")
        return

    if obiezione == "app_gia_fatta_anni_fa":
        await typing(update)
        await update.message.reply_text(f"Qualsiasi bonus app che hai già fatto non può essere rimonetizzata 👍🏻\n\n{domanda_corrente}")
        return

    if obiezione == "sorella_amico":
        await typing(update)
        await update.message.reply_text(f"Se è maggiorenne e ha un documento di identità valido, sì può farlo! Ne parlerete meglio con Luca.\n\n{domanda_corrente}")
        return

    if obiezione == "conto_padre":
        await typing(update)
        await update.message.reply_text(f"Se lui ne è consapevole, sì. Ne parlerai meglio con Luca.\n\n{domanda_corrente}")
        return

    if obiezione == "luca_italiano":
        await typing(update)
        await update.message.reply_text(f"Sì, Luca è italiano 🇮🇹\n\n{domanda_corrente}")
        return

    if obiezione == "straniero":
        await typing(update)
        await update.message.reply_text(f"Non sarà un problema!\n\n{domanda_corrente}")
        return

    if obiezione == "quanto_guadagna_luca":
        await typing(update)
        await update.message.reply_text(f"Non posso riferire queste informazioni.\n\n{domanda_corrente}")
        return

    if obiezione == "social_luca":
        await typing(update)
        await update.message.reply_text(
            "Certo, clicca qui e scopri di più su Luca 👉🏻 [lucapuleo](https://linktr.ee/lucapuleo)",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        await asyncio.sleep(1.0)
        await update.message.reply_text(domanda_corrente)
        return

    if obiezione == "carta_credito":
        await typing(update)
        await update.message.reply_text(f"Non è assolutamente un problema! Non è richiesto un investimento, si inizia da 0. È richiesto solo essere maggiorenni e avere un documento di identità valido.\n\n{domanda_corrente}")
        return

    if obiezione == "quando_contatta":
        await typing(update)
        await update.message.reply_text(f"Ti contatterà lui direttamente il prima possibile! 🔥\n\n{domanda_corrente}")
        return

    if obiezione == "se_non_risponde":
        await typing(update)
        await update.message.reply_text(f"Luca risponde a tutti! Alla fine della nostra conversazione manderò le tue risposte a Luca. Appena possibile ti contatterà e inizierete a fare i bonus.\n\n{domanda_corrente}")
        return

    if obiezione == "perche_chiedi_app":
        await typing(update)
        await update.message.reply_text(f"Perché così riferirò a Luca quale app hai già fatto!\n\n{domanda_corrente}")
        return

    if obiezione == "isybank":
        await typing(update)
        await update.message.reply_text(f"IsyBank è un'applicazione di Intesa SanPaolo 🏦\n\n{domanda_corrente}")
        return

    if obiezione == "n26_satispay":
        await typing(update)
        await update.message.reply_text(f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
        state["step"] = "messaggio_finale"
        state["quali_app_risposta"] = text
        state["app_fatte"] = []
        return

    if obiezione == "diffidenza_online":
        await typing(update)
        await update.message.reply_text(f"Mi dispiace per la brutta esperienza. Con Luca sarà tutto diverso — c'è un motivo se sono +2 anni che aiuta e fa guadagnare le persone, con feedback sempre eccellenti 💪\n\n{domanda_corrente}")
        return

    if obiezione == "equita_luca":
        await typing(update)
        await update.message.reply_text(f"No, Luca guadagna quanto te! Le app pagano gli stessi bonus sia all'invitato che all'invitante. Entrambi guadagnate la stessa cifra 💰\n\n{domanda_corrente}")
        return

    if obiezione == "perche_aiuta":
        await typing(update)
        await update.message.reply_text(f"Luca guadagna solo se guadagni anche tu — quindi è nel suo interesse aiutarti al massimo! È un sistema dove vincono entrambi 🤝\n\n{domanda_corrente}")
        return

    if obiezione == "reddito_cittadinanza":
        await typing(update)
        await update.message.reply_text(f"Per queste domande ti consiglio di informarti con il tuo commercialista 🫱🏻‍🫲🏻\n\n{domanda_corrente}")
        return

    if obiezione == "fiscali_avanzate":
        await typing(update)
        await update.message.reply_text(f"Per queste domande ti consiglio di informarti con il tuo commercialista 🫱🏻‍🫲🏻\n\n{domanda_corrente}")
        return

    if obiezione == "responsabilita":
        await typing(update)
        await update.message.reply_text(f"Non è richiesto nessun investimento, si inizia da 0, sono app gratuite. Non c'è quindi nulla da rimborsare o da perdere 👍🏻\n\n{domanda_corrente}")
        return

    if obiezione == "spalmare_tempo":
        await typing(update)
        await update.message.reply_text(f"Certo, puoi spalmarlo su più giorni! Ti organizzi direttamente con Luca in base alle tue esigenze 🤝\n\n{domanda_corrente}")
        return

    if obiezione == "modalita_assistenza":
        await typing(update)
        await update.message.reply_text(f"Luca ti assiste principalmente tramite messaggi e vocali su Telegram. In casi urgenti può fare anche una chiamata 📱\n\n{domanda_corrente}")
        return

    if obiezione == "persone_anziane":
        await typing(update)
        await update.message.reply_text(f"Certo! La strategia dei bonus app è nata apposta per persone che partono da zero, senza competenze. Luca ha aiutato +400 persone, incluse persone anziane — spiega tutto in modo semplice, step by step 👴🏻👵🏻\n\n{domanda_corrente}")
        return

    if obiezione == "limite_domande":
        await typing(update)
        await update.message.reply_text(f"Quante ne vuoi! Luca è lì apposta per aiutarti 🙌\n\n{domanda_corrente}")
        return

    if obiezione == "computer":
        await typing(update)
        await update.message.reply_text(f"In alcuni casi sì, si può fare anche dal computer o tablet. Ne parlerai direttamente con Luca per capire qual è la soluzione migliore per te 💻\n\n{domanda_corrente}")
        return

    if obiezione == "chiusura_app":
        await typing(update)
        await update.message.reply_text(f"Ti spiegherà tutto Luca — cosa fare e come farlo per ricevere il bonus 👍🏻\n\n{domanda_corrente}")
        return

    if obiezione == "riapertura_app":
        await typing(update)
        await update.message.reply_text(f"In alcuni casi si può riaprire, ma generalmente non otterrai il bonus. Ne parlerai con Luca per valutare la tua situazione specifica 👍🏻\n\n{domanda_corrente}")
        return

    if obiezione == "documenti_altri":
        await typing(update)
        await update.message.reply_text(f"Se hai il suo consenso e usi i suoi dati (documento di identità valido), in alcuni casi è possibile. Ne parlerai meglio con Luca 🫱🏻‍🫲🏻\n\n{domanda_corrente}")
        return

    if obiezione == "sordo_disabile":
        await typing(update)
        await update.message.reply_text(f"Sì, assolutamente! Luca comunica principalmente per messaggio scritto, quindi non ci sono problemi 🙌\n\n{domanda_corrente}")
        return

    if obiezione == "domande_personali_luca":
        await typing(update)
        await update.message.reply_text(f"😄 Quella la salto! Torniamo a noi:\n\n{domanda_corrente}")
        return

    # ── FLUSSO PRINCIPALE ────────────────────────────────────────
    if step == "conosce_bonus":
        if is_yes(text):
            state["conosce_bonus_risposta"] = text
            state["conosce_bonus"] = True
            state["step"] = "ha_fatto_app"
            state["fallback_count"] = 0
            await typing(update)
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        elif is_no(text):
            state["conosce_bonus_risposta"] = text
            state["conosce_bonus"] = False
            state["step"] = "dopo_spiegazione"
            state["fallback_count"] = 0
            await typing(update)
            await update.message.reply_text(
                "Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri e fai dei semplici passaggi insieme a me, "
                "ci riconoscono dei bonus (soldi o buoni amazon) che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, "
                "non è richiesto alcun deposito o spesa, ti dirò quali app usare e cosa fare. Se ci sei iniziamo."
            )
        else:
            state["fallback_count"] = state.get("fallback_count", 0) + 1
            if state["fallback_count"] >= 2:
                paused_leads.add(user_id)
                await typing(update)
                await update.message.reply_text(f"Non preoccuparti {nome}, Luca ti contatterà direttamente 🙌")
                try:
                    await context.bot.send_message(chat_id=LUCA_CHAT_ID, text=f"⚠️ INTERVENTO NECESSARIO\n\n👤 {nome} (@{user.username or user_id})\n🆔 ID: {user_id}\nMessaggio: \"{text}\"\n\nUsa /riprendi {user_id} per gestirlo.")
                except: pass
            else:
                # Prova con Claude API
                risposta_claude = await ask_claude(state, text, step) if ANTHROPIC_API_KEY else None
                if risposta_claude:
                    await typing(update)
                    await update.message.reply_text(risposta_claude)
                else:
                    await typing(update)
                    await update.message.reply_text("Non ho capito bene 😊 Sai già cosa sono i bonus app? Rispondimi con sì o no!")
        return

    if step == "dopo_spiegazione":
        # Dopo la spiegazione, qualsiasi risposta che non sia frustrazione esplicita = vai avanti
        # Il messaggio "Nessun problema" appare solo se il lead dice esplicitamente che non vuole
        if is_no(text) and check_set(text, FRUSTRAZIONI):
            await typing(update)
            await update.message.reply_text(f"Nessun problema {nome}! Se in futuro vuoi saperne di più, Luca è qui 🙌")
            state["step"] = "fine"
        else:
            state["step"] = "ha_fatto_app"
            state["fallback_count"] = 0
            await typing(update)
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        return

    if step == "ha_fatto_app":
        if is_yes(text) or is_no(text) or is_vague(text):
            state["ha_fatto_app_risposta"] = text
            state["ha_fatto_app"] = is_yes(text)
            state["step"] = "quali_app"
            state["fallback_count"] = 0
            await typing(update)
            await update.message.reply_text("Ok! Ti mando la lista delle app disponibili.")
            await update.message.chat.send_action("typing")
            await asyncio.sleep(1.3)
            await send_lista_app(update)
        else:
            state["fallback_count"] = state.get("fallback_count", 0) + 1
            if state["fallback_count"] >= 2:
                paused_leads.add(user_id)
                await typing(update)
                await update.message.reply_text(f"Non preoccuparti {nome}, Luca ti contatterà direttamente 🙌")
                try:
                    await context.bot.send_message(chat_id=LUCA_CHAT_ID, text=f"⚠️ INTERVENTO NECESSARIO\n\n👤 {nome} (@{user.username or user_id})\n🆔 ID: {user_id}\nMessaggio: \"{text}\"\n\nUsa /riprendi {user_id} per gestirlo.")
                except: pass
            else:
                # Prova con Claude API
                risposta_claude = await ask_claude(state, text, step) if ANTHROPIC_API_KEY else None
                if risposta_claude:
                    await typing(update)
                    await update.message.reply_text(risposta_claude)
                else:
                    await typing(update)
                    await update.message.reply_text("Non ho capito 😊 Hai già fatto qualche app in passato? Sì o no!")
        return

    if step == "quali_app":
        state["quali_app_risposta"] = text
        text_upper = text.upper()
        if is_no(text):
            state["app_fatte"] = []
        elif is_vague(text):
            state["app_fatte"] = ["NON RICORDA / INCERTO"]
        else:
            fatte = [app for app in BONUS_LIST if app in text_upper]
            if "BUDDY" in text_upper and "BUDDYBANK" not in fatte: fatte.append("BUDDYBANK")
            if ("AGRICOLE" in text_upper or "CREDIT" in text_upper) and "CREDIT AGRICOLE" not in fatte: fatte.append("CREDIT AGRICOLE")
            if "ISY" in text_upper and "ISYBANK" not in fatte: fatte.append("ISYBANK")
            state["app_fatte"] = list(set(fatte)) if fatte else []

        app_fatte = state.get("app_fatte", [])
        app_mancanti = [a for a in BONUS_LIST if a not in app_fatte]

        state["step"] = "messaggio_finale"
        state["fallback_count"] = 0

        await typing(update)
        if app_fatte and len(app_mancanti) > 0:
            await update.message.reply_text(f"Ok, va bene. Le app restanti le farai con Luca 👍🏻")
            await asyncio.sleep(0.8)

        await update.message.reply_text(f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
        return

    if step == "messaggio_finale":
        state["messaggio_preparazione"] = text
        state["fallback_count"] = 0
        await send_report(context, state, user, tipo="normale")
        nome_completo = f"{user.first_name or ''} {user.last_name or ''}".strip()
        username_str = f"@{user.username}" if user.username else f"ID:{user.id}"
        link_str = f"t.me/{user.username}" if user.username else f"ID:{user.id}"
        append_lead_to_sheet(nome_completo, username_str, link_str)
        state["step"] = "fine"
        await typing(update)
        await update.message.reply_text(
            f"Ottimo {nome}! Ho passato le tue info a Luca, ti contatterà lui direttamente il prima possibile per farti fare tutto passo dopo passo. Preparati 🔥"
        )
        await asyncio.sleep(1.3)
        await update.message.chat.send_action("typing")
        await asyncio.sleep(1.3)
        await update.message.reply_text(
            "Durante l'attesa richiedi l'accesso al gruppo esclusivo di Luca! 👉🏻 [TELEGRAM](https://t.me/+ZU36p4Mf0QFmMTU0)\n\nE seguilo su [INSTAGRAM](https://www.instagram.com/lucapuleo.bsn/)",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return

# ══════════════════════════════════════════════════════════════════
# HANDLE MESSAGGI con delay anti-doppio
# ══════════════════════════════════════════════════════════════════
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in pending_messages:
        try:
            pending_messages[user_id].cancel()
        except: pass

    async def delayed():
        try:
            await asyncio.sleep(1.5)
            await process_message(update, context)
        except asyncio.CancelledError:
            pass

    task = asyncio.ensure_future(delayed())
    pending_messages[user_id] = task

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("riprendi", riprendi))
    app.add_handler(CommandHandler("rec", rec))
    app.add_handler(CommandHandler("contact", contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot avviato ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
