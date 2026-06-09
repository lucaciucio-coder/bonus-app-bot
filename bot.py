import os
import asyncio
import logging
import json
import urllib.request
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IT_TZ = ZoneInfo("Europe/Rome")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
LUCA_CHAT_ID = os.environ.get("LUCA_CHAT_ID", "")
ANTHROPIC_API_KEY = ""  # Claude disabilitato
SHEET_ID = "1JwzOe8PTibniJtZbgM9OgboianmXiuf4PIvD3By6Wz8"

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

BONUS_LIST = ["REVOLUT", "BBVA", "ISYBANK", "BUDDYBANK", "CREDIT AGRICOLE"]
paused_leads = set()
all_leads = []
orange_leads = []
pending_messages = {}
global_states = {}

SPIEGAZIONE_BONUS = "Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri e fai dei semplici passaggi insieme a me, ci riconoscono dei bonus (soldi o buoni amazon) che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, non è richiesto alcun deposito o spesa, ti dirò quali app usare e cosa fare. Se ci sei iniziamo."

# ══════════════════════════════════════════════════════════════════
# RISPOSTE FISSE DA ROLEPLAY
# ══════════════════════════════════════════════════════════════════

RISPOSTE_FISSE = {
    # Tempo
    "tempo": "Mediamente 5–10 minuti per applicazione. Puoi completarle tutte in poco tempo e ricevere i bonus nei tempi indicati dall'app 🕐",
    "solo_sera": "Non è assolutamente un problema! Dopo che avrai risposto a tutte le mie domande, invierò a Luca tutte le tue risposte — ti organizzerai direttamente con lui per l'orario 🤝",
    # Soldi
    "soldi": "Assolutamente no! Non è richiesto un investimento, si inizia da 0. Sono app gratuite. È richiesto solo essere maggiorenni e avere un documento di identità valido.",
    # Sicurezza
    "sicurezza": "Sono app ufficiali di banche e fintech regolamentate — nessun problema.",
    "virus": "Sì, le scarichi dal App Store o Google Play Store — niente virus. Sono app bancarie ufficiali! Non scaricarle adesso però, per sbloccare i bonus devi seguire tutti i passaggi di Luca 📱",
    "dati": "Non devi dare i tuoi dati personali a Luca — la registrazione la fai tu, le credenziali restano in mano a te!",
    "furto": "Non possono rubarti i soldi — non è mai successo. Sono app bancarie ufficiali e verificate!",
    "accesso_conto": "No, queste app non hanno accesso al tuo conto corrente principale.",
    "conto_bloccato": "Se segui tutti i passaggi che ti dirà Luca e non infranga le regole delle app, non succede!",
    # Luca
    "perche_aiuta": "Le app pagano i bonus sia a te che a Luca — per questo è nel suo interesse aiutarti al massimo!",
    "luca_guadagna_piu": "No, Luca guadagna quanto te! Le app pagano gli stessi bonus sia all'invitato che all'invitante.",
    "luca_chi_e": "Luca è un ragazzo che da +3 anni lavora nel mondo online e dei bonus app. Ha ottenuto ottimi risultati e aiutato +400 persone a passare da 0 ai primi guadagni online.",
    "luca_italiano": "Sì, Luca è italiano 🇮🇹",
    "luca_social": "Certo, clicca qui e scopri di più su Luca 👉🏻 linktr.ee/lucapuleo",
    "luca_non_risponde": "Luca risponde a tutti! Alla fine della nostra conversazione manderò le tue risposte a Luca. Appena possibile ti contatterà e inizierete a fare i bonus.",
    "quando_contatta": "Ti contatterà lui direttamente il prima possibile! 🔥",
    "assistenza_modalita": "Luca ti assiste principalmente tramite messaggi e vocali su Telegram. In casi urgenti può fare anche una chiamata 📱",
    # App
    "app_gia_aperta": "Non è un problema! In questo caso però non potrai sbloccare quel bonus, perché è un'app che hai già. Otterrai i bonus delle app restanti 💰",
    "app_gia_fatta_anni": "In alcuni casi si può riaprire, ma generalmente non otterrai il bonus. Ne parlerai con Luca per valutare la tua situazione 👍🏻",
    "app_tutte": "Ok! Parlerai con Luca su come procedere.",
    "fregato_online": "Mi dispiace per la brutta esperienza. Con Luca sarà tutto diverso — c'è un motivo se sono +2 anni che aiuta e fa guadagnare le persone, con feedback sempre eccellenti 💪",
    "recensioni": "Certo che puoi! Per vedere i feedback entra nel suo canale Telegram o seguilo su Instagram.",
    "isybank": "IsyBank è un'applicazione di Intesa SanPaolo 🏦",
    "app_dal_computer": "In alcuni casi sì, si può fare anche dal computer o tablet. Ne parlerai direttamente con Luca 💻",
    "telefono_vecchio": "Verificherai direttamente con Luca la compatibilità.",
    "sistema_operativo": "Funziona sia su iPhone che su Android 📱",
    "posso_smettere": "Assolutamente sì, puoi smettere di fare i bonus quando vuoi — nessun vincolo!",
    "app_restano": "Le app restano sul telefono finché arriva il bonus, poi se vuoi puoi disinstallarle 👍🏻",
    "chiusura_app": "Ti spiegherà tutto Luca — cosa fare e come farlo per ricevere il bonus 👍🏻",
    "bonus_arriva": "Sì! I bonus vengono accreditati direttamente sull'app che hai aperto — in pochi giorni. Una volta ricevuti, Luca ti spiega come trasferirli sul tuo conto 💸",
    # Documenti e requisiti
    "minorenne": "Purtroppo no, i bonus app sono solo per i maggiorenni. Puoi effettuare le registrazioni con i documenti di qualcun altro (maggiorenne), ma ricorda che devi avere il suo CONSENSO!",
    "documento": "Serve un documento di identità valido (carta di identità + tessera sanitaria) ed essere maggiorenni.",
    "carta_credito": "Non è assolutamente un problema! Non è richiesto un investimento, si inizia da 0. È richiesto solo essere maggiorenni e avere un documento di identità valido.",
    "conto_in_rosso": "Valuterai direttamente con Luca per questo tipo di condizioni.",
    "estero": "Se sei italiano/a e vivi all'estero, potrai sbloccare solo determinati bonus. Ne parlerai meglio con Luca.",
    "straniero": "Non sarà un problema!",
    # Famiglia
    "sorella_amico": "Se è maggiorenne e ha un documento di identità valido, sì può farlo! Ne parlerete meglio con Luca.",
    "conto_padre": "Se lui ne è consapevole, sì. Ne parlerai meglio con Luca.",
    "sordo": "Sì, assolutamente! Luca comunica principalmente per messaggio scritto 🙌",
    # Anziani
    "anziani": "Certo! La strategia dei bonus app è nata apposta per persone che partono da zero, senza competenze. Luca ha aiutato +400 persone, incluse persone anziane — spiega tutto in modo semplice, step by step 👴🏻👵🏻",
    "limite_domande": "Quante ne vuoi! Luca è lì apposta per aiutarti 🙌",
    # Guadagno
    "guadagno_totale": "Dipende dalle app attive al momento, in media +150€ 💰",
    "guadagno_luca": "Non posso riferire queste informazioni.",
    "fiscale": "Per queste domande ti consiglio di informarti con il tuo commercialista 🫱🏻‍🫲🏻",
    "reddito_cittadinanza": "Per queste domande ti consiglio di informarti con il tuo commercialista 🫱🏻‍🫲🏻",
    # Particolari
    "rimborso": "Non è richiesto nessun investimento, si inizia da 0. Di conseguenza non c'è nessun rimborso.",
    "piu_tardi": "Sì, appena finiamo la conversazione manderò a Luca le tue risposte, lui ti contatterà e vi metterete d'accordo per l'orario 🤝",
    "piu_tardi_quando": "Non posso darti un orario preciso, lavora con molte persone. Al più presto ti contatterà!",
    "paura_sbagliare": "Luca ti seguirà passo dopo passo — se lo segui non puoi sbagliare nulla 💪",
    "davanti_telefono": "No, non serve. Mediamente ci vogliono 5–10 minuti per app.",
    "spalmare_tempo": "Certo, puoi spalmarlo su più giorni! Ti organizzi direttamente con Luca in base alle tue esigenze 🤝",
    "faccio_ora": "Ogni passaggio lo farai con Luca, non da solo/a.",
    "scommesse": "No, sono app di banche e fintech ufficiali (tipo Revolut, BBVA, Intesa SanPaolo) — zero scommesse, solo bonus per registrazione.",
    "luca_non_esiste": "Certo, clicca qui e scopri di più su Luca 👉🏻 linktr.ee/lucapuleo",
    "perche_chiedi_app": "Perché così riferirò a Luca quale app hai già fatto!",
    "responsabilita": "Non è richiesto nessun investimento, si inizia da 0. Non c'è quindi nulla da perdere 👍🏻",
    "domande_personali": "😄 Quella la salto! Torniamo a noi:",
    "documenti_altri": "Se hai il suo consenso e usi i suoi dati (documento di identità valido), in alcuni casi è possibile. Ne parlerai meglio con Luca 🫱🏻‍🫲🏻",
}

# Parole chiave → categoria risposta
KEYWORDS_RISPOSTA = {
    "tempo": ["quanto tempo", "quanto ci vuole", "quanto dura", "quanto impiego", "ci vuole molto", "è lungo", "è veloce", "5 minuti", "10 minuti", "in quanto"],
    "solo_sera": ["solo la sera", "solo di sera", "lavoro tutto il giorno", "ho tempo solo", "solo il weekend", "sono impegnato", "ho una vita", "ho impegni", "non ho molto tempo"],
    "soldi": ["non ho soldi", "non ho budget", "costa qualcosa", "quanto costa", "ci vogliono soldi", "non posso permettermi", "sono al verde", "non ho disponibilità", "devo investire", "serve investimento", "devo depositare", "non ho soldi da depositare", "deposito", "investimento"],
    "sicurezza": ["è sicuro", "è legale", "garanzie", "è affidabile", "prove", "non mi fido", "truffa", "sono truffe", "non è che sono truffe", "non sarà una truffa"],
    "virus": ["ci sono virus", "non voglio virus", "è sicuro scaricare", "ha virus", "dove si scarica", "si trova su app store", "si trova su play store"],
    "dati": ["dati personali", "le mie informazioni", "privacy", "credenziali", "password", "non voglio dare i miei dati"],
    "furto": ["rubano i soldi", "svuotano il conto", "possono rubarmi", "perdere i soldi"],
    "accesso_conto": ["accesso al conto", "vedono il conto", "accedono al conto", "accesso al mio conto"],
    "conto_bloccato": ["bloccano il conto", "conto bloccato", "rischio blocco"],
    "perche_aiuta": ["perché mi aiuti gratis", "cosa ci guadagni", "perché dovrebbe aiutarmi", "gratis perché", "dov'è la fregatura", "qual è la fregatura", "fregatura", "troppo bello per essere vero"],
    "luca_guadagna_piu": ["luca guadagna di più", "non mi sembra equo", "mi sfrutta", "mi usa", "guadagna grazie a me"],
    "luca_chi_e": ["chi è luca", "luca chi è", "non conosco luca", "come faccio a fidarmi di luca"],
    "luca_italiano": ["luca è italiano", "luca parla italiano", "di dove è luca"],
    "luca_social": ["profilo social", "instagram di luca", "dove trovo luca", "luca esiste", "voglio verificare luca", "linktr"],
    "luca_non_risponde": ["se luca non risponde", "e se non risponde", "non risponde mai"],
    "quando_contatta": ["quando mi contatta", "ho fretta", "quanto aspetto", "quando mi scrivi", "quando mi chiama"],
    "assistenza_modalita": ["come mi spiega", "in chiamata", "per messaggio", "come comunichiamo", "vocali", "videochiamata"],
    "app_gia_aperta": ["ho già revolut", "ho già bbva", "ho già buddy", "ho già isybank", "ho già credit agricole", "ce l'ho già", "l'ho già aperta", "ho già quel conto"],
    "app_gia_fatta_anni": ["l'ho già fatta anni fa", "l'avevo già fatta", "già fatta in passato", "la feci tempo fa", "ho già quel conto da anni"],
    "app_tutte": ["le ho fatte tutte", "ho già tutte", "tutte le ho fatte"],
    "fregato_online": ["mi hanno già fregato", "ho già perso soldi online", "ho già provato e non ha funzionato", "non funziona mai", "solita storia", "l'ho già sentito", "ho già sentito questa storia"],
    "recensioni": ["recensioni", "feedback", "testimonianze", "voglio prove", "qualcuno che ha già guadagnato", "screenshot"],
    "isybank": ["cos'è isybank", "isybank cos'è", "non conosco isybank", "isybank di cosa è"],
    "app_dal_computer": ["dal computer", "dal pc", "ho il telefono rotto", "ho solo il computer", "tablet"],
    "telefono_vecchio": ["telefono vecchio", "telefono datato", "non so se supporta"],
    "sistema_operativo": ["iphone o android", "funziona su iphone", "è per android", "anche per iphone", "ho un iphone", "ho un android", "ho un samsung"],
    "posso_smettere": ["posso smettere", "posso fermarmi", "sono obbligato", "ci sono vincoli", "rimango bloccato"],
    "app_restano": ["restano sul telefono", "devo tenerle", "posso disinstallarle", "le elimino dopo"],
    "chiusura_app": ["se chiudo l'app", "devo tenerla aperta", "posso chiuderla subito", "è sufficiente aprirla"],
    "bonus_arriva": ["i bonus arrivano davvero", "si ricevono davvero", "ma pagano davvero", "quando arrivano i bonus", "dove arrivano i soldi"],
    "minorenne": ["sono minorenne", "ho meno di 18", "non ho 18 anni", "ho 16 anni", "ho 17 anni", "non sono maggiorenne"],
    "documento": ["non ho documento", "documento scaduto", "non ho carta di identità", "quali documenti servono", "cosa serve"],
    "carta_credito": ["non ho la carta di credito", "ho solo il bancomat", "serve la carta", "ho solo prepagata", "ho solo postepay"],
    "conto_in_rosso": ["ho il conto in rosso", "sono in rosso", "conto scoperto", "ho debiti"],
    "estero": ["vivo all'estero", "sono all'estero", "non sono in italia", "sono emigrato"],
    "straniero": ["sono straniero", "non sono italiano", "parlo poco italiano", "non capisco bene l'italiano"],
    "sorella_amico": ["mia sorella", "mio fratello", "un mio amico", "mia moglie", "mio marito", "mio padre", "mia madre", "un familiare", "qualcun altro"],
    "conto_padre": ["conto di mio padre", "conto di mia moglie", "conto di qualcun altro", "con i dati di"],
    "sordo": ["sono sordo", "sono sorda", "non sento", "ho problemi di udito"],
    "anziani": ["ho tanti anni", "sono anziano", "sono anziana", "ho 60 anni", "ho 65 anni", "ho 70 anni", "sono in pensione", "non sono giovane", "non sono pratico di tecnologia"],
    "limite_domande": ["posso fare quante domande", "posso chiedere sempre", "c'è un limite alle domande"],
    "guadagno_totale": ["quanto si guadagna in totale", "quanto posso guadagnare", "quanti soldi si fanno", "quanto fa in tutto", "totale bonus", "in media quanto"],
    "guadagno_luca": ["quanto ha guadagnato luca", "quanto guadagna luca", "i guadagni di luca"],
    "fiscale": ["fiscalmente", "devo dichiarare", "tasse", "irpef", "commercialista", "agenzia delle entrate"],
    "reddito_cittadinanza": ["reddito di cittadinanza", "naspi", "sussidi", "disoccupazione", "isee", "rdc", "ammortizzatori"],
    "rimborso": ["mi rimborsa", "chi paga se va male", "garanzia di guadagno", "e se non guadagno"],
    "piu_tardi": ["non ho tempo adesso", "posso farlo più tardi", "lo faccio dopo", "in un secondo momento"],
    "piu_tardi_quando": ["tra quanto", "stasera o domani", "quando mi contatta di preciso"],
    "paura_sbagliare": ["ho paura di sbagliare", "e se sbaglio", "e se faccio un errore", "non voglio sbagliare"],
    "davanti_telefono": ["devo stare davanti al telefono", "devo essere presente", "devo farlo tutto insieme"],
    "spalmare_tempo": ["posso spalmarlo", "posso farlo su più giorni", "devo farlo tutto in un giorno", "posso farlo a tappe"],
    "faccio_ora": ["lo faccio ora", "voglio iniziare subito", "posso iniziare adesso", "partiamo subito", "iniziamo subito", "quando si fa", "facciamo adesso"],
    "scommesse": ["scommesse", "giochi", "casino", "slot", "poker", "betting"],
    "luca_non_esiste": ["luca esiste davvero", "come faccio a sapere che esiste", "voglio vedere chi è"],
    "perche_chiedi_app": ["perché mi chiedi delle app", "a cosa serve sapere", "perché vuoi sapere"],
    "responsabilita": ["chi mi rimborsa", "chi risponde", "luca si prende la responsabilità"],
    "domande_personali": ["luca è single", "luca ha la fidanzata", "quanti anni ha luca", "dove vive luca"],
    "documenti_altri": ["con il numero di telefono di", "con i dati di mia", "usando il documento di", "con il documento di"],
}

def get_risposta_fissa(text: str) -> tuple:
    """Restituisce (categoria, risposta) se il testo corrisponde a una casistica"""
    t = text.strip().lower()
    for categoria, keywords in KEYWORDS_RISPOSTA.items():
        for kw in keywords:
            if kw in t:
                risposta = RISPOSTE_FISSE.get(categoria)
                if risposta:
                    return categoria, risposta
    return None, None

LISTA_APP_MD = (
    "*BONUS ATTIVI*\n\n"
    "*__REVOLUT__*\n15€\n\n"
    "*__BBVA__*\n10€\n\n"
    "*__ISYBANK__*\n30€ BUONO AMAZON\n\n"
    "*__BUDDYBANK__*\n50€\n\n"
    "*__CREDIT AGRICOLE__*\n50€ BUONO AMAZON\n\n"
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
# CASISTICHE FISSE
# ══════════════════════════════════════════════════════════════════

# Risposte chiare = sì
CHIARAMENTE_SI = {
    "si", "sì", "ok", "okay", "va bene", "vabene", "certo", "sisi",
    "yes", "yep", "yeah", "dai", "esatto", "giusto", "confermo",
    "già", "assolutamente", "certamente", "ovviamente", "naturalmente",
    "perfetto", "d'accordo", "daccordo", "capito", "chiaro", "ho capito",
    "ok capito", "ok ho capito", "ah ok", "ok dai", "procedi", "vai",
    "andiamo", "iniziamo", "partiamo", "ci sono", "ci sto",
    "👍", "✅", "💪", "🔥", "top", "siuro",
    # App già fatte esplicite
    "ho fatto revolut", "ho fatto bbva", "ho fatto buddy", "ho fatto buddybank",
    "ho fatto isybank", "ho fatto krak", "ho fatto credit agricole",
    "ho già revolut", "ho già bbva", "ho già buddy", "ho già krak",
    "revolut sì", "bbva sì", "buddy sì", "krak sì",
    "revolut si", "bbva si", "buddy si", "krak si",
    # Quantità
    "qualcuna", "una o due", "un paio", "alcune", "ne ho fatta qualcuna",
    "ho fatto qualcosa", "già fatto", "ho esperienza",
    "1", "2", "3", "4", "5", "una", "due", "tre",
}

# Risposte chiare = no
CHIARAMENTE_NO = {
    "no", "nope", "nessuna", "mai", "niente", "zero",
    "non ne ho fatta nessuna", "non ho mai fatto",
    "non le conosco", "non ho mai usato",
    "nah", "na", "nulla", "assolutamente no",
    "non ancora", "ancora nessuna", "per ora nessuna",
    # Non conosce i bonus
    "non lo so", "non so cosa sono", "non ne so niente",
    "non ho idea", "non so", "non capisco",
    "mai sentito", "prima volta", "parto da zero",
    "non tanto", "non proprio", "mah dipende",
    "non molto", "quasi no", "direi di no",
}

# Frasi dopo cui il bot sa con certezza cosa rispondere
FRUSTRAZIONI_ESPLICITE = {
    "lascia perdere", "lascia stare", "non mi interessa più",
    "non voglio più", "ho cambiato idea", "non fa per me",
    "arrivederci", "bye", "goodbye", "non me ne frega",
    "non voglio continuare", "smetto qui",
}

def is_clear_yes(text: str) -> bool:
    t = text.strip().lower()
    if t in CHIARAMENTE_SI:
        return True
    for app in ["revolut", "bbva", "isybank", "buddybank", "buddy", "credit agricole", "krak"]:
        if app in t and len(t.split()) <= 5:
            return True
    return False

def is_clear_no(text: str) -> bool:
    t = text.strip().lower()
    if t in CHIARAMENTE_NO:
        return True
    for kw in CHIARAMENTE_NO:
        if len(kw) > 4 and kw in t:
            return True
    return False

def is_frustrazione(text: str) -> bool:
    t = text.strip().lower()
    for kw in FRUSTRAZIONI_ESPLICITE:
        if kw in t:
            return True
    return False

def get_state(context):
    if "state" not in context.user_data:
        context.user_data["state"] = {}
    return context.user_data["state"]

def calcola_punteggio(state):
    punti = 0
    if state.get("conosce_bonus"): punti += 3
    if state.get("ha_fatto_app"): punti += 3
    app_fatte = state.get("app_fatte", [])
    if app_fatte and app_fatte != ["NON RICORDA"]:
        punti += min(len(app_fatte), 3)
    if punti >= 7: return punti, "🔥 HOT"
    elif punti >= 4: return punti, "🟡 WARM"
    else: return punti, "🔵 COLD"

async def typing(update, seconds=1.3):
    await update.message.chat.send_action("typing")
    await asyncio.sleep(seconds)

# ══════════════════════════════════════════════════════════════════
# CLAUDE — AIUTANTE (solo per casi ambigui)
# ══════════════════════════════════════════════════════════════════

CLAUDE_SYSTEM = """Sei l'assistente personale di Luca Puleo che gestisce lead interessati ai bonus app.

CONTESTO BONUS APP:
- App gratuite di banche/fintech ufficiali che pagano bonus per nuove registrazioni
- Zero investimento, si parte da 0
- Serve: maggiorenni, documento identità valido (CI + tessera sanitaria)
- 5-10 min per app, spalmabili su più giorni
- Bonus accreditati in pochi giorni, poi Luca spiega come trasferirli
- Guadagno medio lead: +150€ totali
- App: REVOLUT (15€), BBVA (10€), ISYBANK/Intesa SanPaolo (30€ buono Amazon), BUDDYBANK (50€), CREDIT AGRICOLE (50€ buono Amazon), KRAK (10$)

RISPOSTE FISSE — usale ESATTAMENTE così:

SPIEGAZIONE BASE — USALA PAROLA PER PAROLA, nessuna variante:
"Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri e fai dei semplici passaggi insieme a me, ci riconoscono dei bonus (soldi o buoni amazon) che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, non è richiesto alcun deposito o spesa, ti dirò quali app usare e cosa fare."
NOTA: questa frase la manda il bot in automatico. TU non la devi mai riscrivere o parafrasare.
Se dopo la spiegazione chiedono altri dettagli su come funziona:
"Insieme a Luca, scarichi le app, completi la registrazione in 5-10 minuti, segui i passaggi che ti dice Luca e ricevi il bonus nei tempi stabiliti dall'app — zero investimento, app ufficiali di banche."

SCOMMESSE/GIOCHI → "No, sono app di banche e fintech ufficiali (tipo Revolut, BBVA, Intesa SanPaolo) — zero scommesse, solo bonus per registrazione." + poi aggiungi la SPIEGAZIONE BASE

SOLDI/INVESTIMENTO/DEPOSITO → "Assolutamente no! Non è richiesto un investimento, si inizia da 0. Sono app gratuite."

TRUFFA/SICUREZZA → "Sono app ufficiali di banche e fintech regolamentate — nessun problema."
IMPORTANTE: NON dire mai "zero rischi" — non usare mai questa frase.

POSSO FARLO ORA / VOGLIO INIZIARE SUBITO / QUANDO SI FA → "Ogni passaggio lo farai con Luca, non da solo/a."

SOLO SE chiedono "perché mi aiuti gratis" o "cosa ci guadagni" → "Le app pagano bonus sia a te che a Luca — per questo ti aiuta gratis."
MAI in altri contesti.

Quanto guadagna Luca → "Non posso riferire queste informazioni."
Luca guadagna di più → "No, guadagnate la stessa cifra."
Quanto tempo → "5-10 minuti per app."
Quando posso farlo → "Quando vuoi, ti organizzi con Luca."
Minorenne → "Solo maggiorenni. Con consenso puoi usare documenti di qualcuno maggiorenne."
Domande fiscali/ISEE/NASPI/RDC → "Informati con il tuo commercialista."
Dettagli tecnici app → "Ne parlerai con Luca."
Quando contatta → "Il prima possibile."
Recensioni → "Entra nel canale Telegram o seguilo su Instagram."
Profilo Luca → "linktr.ee/lucapuleo"
iPhone/Android → "Entrambi."
App già aperta → "Non potrai sbloccare quel bonus ma farai le altre."
Ho già fatto tutte → "Ok! Parlerai con Luca su come procedere."
Fregato online → "Con Luca è diverso — +2 anni, +400 persone aiutate."
Domande personali su Luca → 😄 e vai avanti
Posso smettere → "Sì, quando vuoi."
Dati personali → "Le credenziali restano a te."

REGOLE CRITICHE:
1. Risposte BREVI — max 2 righe
2. Dopo la risposta fai DIRETTAMENTE la prossima domanda del flusso — MAI "vuoi procedere?" o "hai capito?"
3. Non inventare mai informazioni
4. Tono: amichevole, diretto
5. Rispondi SEMPRE in italiano
6. NON dire mai "zero rischi"
7. NON menzionare mai i guadagni di Luca a meno che non lo chiedano esplicitamente
8. NON dare mai giorni certi per i bonus — di solo "in pochi giorni" senza specificare quanti
9. NON chiudere mai la conversazione da solo — non dire mai "contatta Luca", "scrivi a Luca", "siamo pronti" — quella decisione spetta al bot
10. Dopo ogni risposta torna SEMPRE alla domanda del flusso corrente che ti viene passata

Rispondi SOLO con il testo da mandare al lead. Nient'altro."""

async def chiedi_claude(state: dict, text: str, domanda_corrente: str) -> str:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        step = state.get("step", "")
        nome = state.get("nome", "il lead")

        step_to_next = {
            "conosce_bonus": "Hai già fatto qualche app in passato?",
            "dopo_spiegazione": "Hai già fatto qualche app in passato?",
            "ha_fatto_app": "Hai già fatto qualche app in passato?",
            "quali_app": f"C'è qualcosa che vorresti far sapere a Luca prima di iniziare?",
            "messaggio_finale": "",
        }
        prossima_domanda = step_to_next.get(step, domanda_corrente)

        # Storico ultime 4 interazioni Claude
        history = state.get("history", [])
        history_str = ""
        if history:
            history_str = "\nULTIME RISPOSTE GIÀ DATE (NON ripetere le stesse cose):\n"
            for h in history[-4:]:
                history_str += f"Lead: {h['lead']}\nBot: {h['bot']}\n"

        prompt = f"""Il lead si chiama {nome}. Step corrente: {step}.
{history_str}
Messaggio attuale del lead: "{text}"

Rispondi brevemente (max 2 righe) tenendo conto di quello che hai già detto sopra — non ripetere le stesse risposte.
Poi fai questa domanda: "{prossima_domanda}" """

        payload = json.dumps({
            "model": "claude-haiku-4-5",
            "max_tokens": 200,
            "system": CLAUDE_SYSTEM,
            "messages": [{"role": "user", "content": prompt}]
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
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["content"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Errore Claude API: {e}")
        return None

# ══════════════════════════════════════════════════════════════════
# REPORT E SHEETS
# ══════════════════════════════════════════════════════════════════

async def send_report(context, state, user_obj, tipo="normale"):
    if hasattr(user_obj, 'username') and user_obj.username:
        contatto = f"👤 @{user_obj.username} — [Contatta](https://t.me/{user_obj.username})"
    else:
        contatto = f"👤 Nome: {state.get('nome')} — Nessun username (ID: {getattr(user_obj, 'id', '?')})"

    punteggio, categoria = calcola_punteggio(state)
    intestazione = "🔔 NUOVO LEAD QUALIFICATO" if tipo == "normale" else "🟠 NUOVO LEAD DA CONTATTARE"

    report = (
        f"{intestazione}\n\n{contatto}\n──────────────\n"
        f"*Sapeva cos'erano i bonus app?* _\"{state.get('conosce_bonus_risposta', '—')}\"_\n-\n"
        f"*Aveva già fatto app in passato?* _\"{state.get('ha_fatto_app_risposta', '—')}\"_\n-\n"
        f"*App già fatte:* _\"{state.get('quali_app_risposta', '—')}\"_\n──────────────\n\n"
        f"💬 Messaggio preparazione: _\"{state.get('messaggio_preparazione', '—')}\"_\n\n"
        f"📊 Punteggio: *{punteggio}/10* — {categoria}"
    )

    entry = {"report": report, "tipo": tipo, "time": datetime.now(IT_TZ)}
    if tipo == "normale": all_leads.append(entry)
    else: orange_leads.append(entry)

    try:
        await context.bot.send_message(chat_id=LUCA_CHAT_ID, text=report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Errore report: {e}")

async def esegui_fine(update, context, state, user):
    nome = state.get("nome", "")
    await send_report(context, state, user, tipo="normale")
    nome_completo = f"{user.first_name or ''} {user.last_name or ''}".strip()
    append_lead_to_sheet(nome_completo,
        f"@{user.username}" if user.username else f"ID:{user.id}",
        f"t.me/{user.username}" if user.username else f"ID:{user.id}")
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
        parse_mode="Markdown", disable_web_page_preview=True
    )

# ══════════════════════════════════════════════════════════════════
# JOB TIMERS
# ══════════════════════════════════════════════════════════════════

async def followup_4h(context):
    data = context.job.data
    state_ref = data["state_ref"]
    if state_ref.get("step") in ("fine", None): return
    last = state_ref.get("last_message_time")
    if last and (datetime.now(IT_TZ) - last).total_seconds() < 4 * 3600 - 60: return
    try:
        await context.bot.send_chat_action(chat_id=data["chat_id"], action="typing")
        await asyncio.sleep(1.3)
        await context.bot.send_message(chat_id=data["chat_id"], text=f"Ciao {data['nome']}, sei ancora lì? Luca ti aspetta 👀")
    except Exception as e:
        logger.error(f"Errore follow-up 4h: {e}")

async def report_24h(context):
    data = context.job.data
    state_ref = data["state_ref"]
    if state_ref.get("step") == "fine": return
    last = state_ref.get("last_message_time")
    if last and (datetime.now(IT_TZ) - last).total_seconds() < 24 * 3600 - 60: return
    await send_report(context, state_ref, data["user_obj"], tipo="arancione")

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
    state["history"] = []  # Storico conversazione per Claude
    global_states[user_id] = state

    job_data = {"chat_id": user_id, "nome": first_name, "state_ref": state, "user_obj": user}
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
# PROCESS MESSAGE — Bot decide, Claude aiuta
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

    # ── CONTROLLA RISPOSTE FISSE DA ROLEPLAY ─────────────────────
    categoria, risposta_fissa = get_risposta_fissa(text)
    if risposta_fissa:
        domanda_corrente = {
            "conosce_bonus": "Sai come funzionano i bonus app?",
            "dopo_spiegazione": "Hai già fatto qualche app in passato?",
            "ha_fatto_app": "Hai già fatto qualche app in passato?",
            "quali_app": "Hai già fatto qualcuna di queste app?",
            "messaggio_finale": f"C'è qualcosa che vorresti far sapere a Luca prima di iniziare?",
        }.get(step, "")
        await typing(update)
        if domanda_corrente:
            await update.message.reply_text(f"{risposta_fissa}\n\n{domanda_corrente}")
        else:
            await update.message.reply_text(risposta_fissa)
        return

    # ── FRUSTRAZIONE ESPLICITA ────────────────────────────────────
    if is_frustrazione(text):
        await typing(update)
        await update.message.reply_text(f"Capito {nome}! Se cambi idea sono qui 🙌")
        state["step"] = "fine"
        try:
            await context.bot.send_message(
                chat_id=LUCA_CHAT_ID,
                text=f"🔴 LEAD PERSO\n\n👤 {nome} (@{user.username or user_id})\nUltimo messaggio: \"{text}\""
            )
        except: pass
        return

    # ══════════════════════════════════════════════════════════════
    # STEP 1 — Sai come funzionano i bonus app?
    # ══════════════════════════════════════════════════════════════
    if step == "conosce_bonus":
        if is_clear_yes(text):
            state["conosce_bonus"] = True
            state["conosce_bonus_risposta"] = text
            state["step"] = "ha_fatto_app"
            await typing(update)
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        elif is_clear_no(text):
            state["conosce_bonus"] = False
            state["conosce_bonus_risposta"] = text
            state["step"] = "dopo_spiegazione"
            await typing(update)
            await update.message.reply_text(SPIEGAZIONE_BONUS)
        else:
            # Ambiguo o domanda — Claude risponde e poi manda la spiegazione
            risposta = await chiedi_claude(state, text, "Sai come funzionano i bonus app?")
            if risposta:
                # Se Claude ha risposto a un'obiezione, vai avanti con spiegazione
                if "history" not in state: state["history"] = []
                state["history"].append({"lead": text, "bot": risposta})
                await typing(update)
                await update.message.reply_text(risposta)
                await asyncio.sleep(1.0)
                await update.message.chat.send_action("typing")
                await asyncio.sleep(1.3)
                await update.message.reply_text(SPIEGAZIONE_BONUS)
            else:
                await typing(update)
                await update.message.reply_text(SPIEGAZIONE_BONUS)
            state["step"] = "dopo_spiegazione"
        return

    # ══════════════════════════════════════════════════════════════
    # STEP 1b — Dopo spiegazione
    # ══════════════════════════════════════════════════════════════
    if step == "dopo_spiegazione":
        if is_clear_yes(text):
            state["step"] = "ha_fatto_app"
            await typing(update)
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        elif is_frustrazione(text):
            await typing(update)
            await update.message.reply_text(f"Nessun problema {nome}! Se cambi idea sono qui 🙌")
            state["step"] = "fine"
        else:
            # Claude gestisce obiezioni o risposte ambigue
            risposta = await chiedi_claude(state, text, "Hai capito come funzionano i bonus app? Vuoi procedere?")
            if risposta:
                if "history" not in state: state["history"] = []
                state["history"].append({"lead": text, "bot": risposta})
                await typing(update)
                await update.message.reply_text(risposta)
                state["step"] = "ha_fatto_app"
            else:
                state["step"] = "ha_fatto_app"
                await typing(update)
                await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        return

    # ══════════════════════════════════════════════════════════════
    # STEP 2 — Hai già fatto qualche app in passato?
    # ══════════════════════════════════════════════════════════════
    if step == "ha_fatto_app":
        t_lower = text.strip().lower()
        # Parole che vanno direttamente alla lista senza passare da Claude
        vai_alla_lista = [
            "forse", "forse qualcuna", "forse una", "forse due",
            "non ricordo", "non mi ricordo", "boh", "mah",
            "non so", "non saprei", "dipende",
            "qualcosa", "qualcosa ho fatto", "credo di sì", "credo di si",
            "penso di sì", "penso di si", "non sono sicuro", "non sono sicura",
            "più o meno", "piu o meno", "tipo sì", "tipo si",
        ]
        is_vai_lista = any(kw in t_lower for kw in vai_alla_lista)

        if is_clear_yes(text) or is_clear_no(text) or is_vai_lista:
            state["ha_fatto_app"] = is_clear_yes(text) or is_vai_lista
            state["ha_fatto_app_risposta"] = text
            state["step"] = "quali_app"
            await typing(update)
            await update.message.reply_text("Ok! Ti mando la lista delle app disponibili.")
            await asyncio.sleep(1.3)
            await update.message.chat.send_action("typing")
            await asyncio.sleep(1.3)
            await update.message.reply_text(LISTA_APP_MD, parse_mode="MarkdownV2")
        else:
            # Claude gestisce solo domande/obiezioni vere
            risposta = await chiedi_claude(state, text, "Hai già fatto qualche app in passato?")
            if risposta:
                if "history" not in state: state["history"] = []
                state["history"].append({"lead": text, "bot": risposta})
                await typing(update)
                await update.message.reply_text(risposta)
            else:
                state["ha_fatto_app_risposta"] = text
                state["step"] = "quali_app"
                await typing(update)
                await update.message.reply_text("Ok! Ti mando la lista delle app disponibili.")
                await asyncio.sleep(1.3)
                await update.message.chat.send_action("typing")
                await asyncio.sleep(1.3)
                await update.message.reply_text(LISTA_APP_MD, parse_mode="MarkdownV2")
        return

    # ══════════════════════════════════════════════════════════════
    # STEP 3 — Hai già fatto qualcuna di queste app?
    # ══════════════════════════════════════════════════════════════
    if step == "quali_app":
        t_upper = text.upper()
        t_lower = text.lower()

        # Riconosci app nella risposta
        fatte = []
        if "REVOLUT" in t_upper: fatte.append("REVOLUT")
        if "BBVA" in t_upper: fatte.append("BBVA")
        if "ISY" in t_upper: fatte.append("ISYBANK")
        if "BUDDY" in t_upper: fatte.append("BUDDYBANK")
        if "AGRICOLE" in t_upper or "CREDIT" in t_upper: fatte.append("CREDIT AGRICOLE")
        if "KRAK" in t_upper: fatte.append("KRAK")

        is_no_app = any(kw in t_lower for kw in ["no", "nessuna", "niente", "mai", "zero", "nulla"])
        is_all_app = any(kw in t_lower for kw in ["tutte", "tutte quante", "le ho fatte tutte"])
        is_ambiguous = not fatte and not is_no_app and not is_all_app

        if is_all_app:
            state["quali_app_risposta"] = text
            state["app_fatte"] = ["LE HA FATTE TUTTE"]
            state["step"] = "messaggio_finale"
            await typing(update)
            await update.message.reply_text(f"Ok! Parlerai con Luca su come procedere.\n\nOttimo {nome}! C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
        elif fatte or is_no_app:
            state["quali_app_risposta"] = text
            state["app_fatte"] = fatte if fatte else []
            app_mancanti = [a for a in BONUS_LIST if a not in fatte]
            state["step"] = "messaggio_finale"
            await typing(update)
            if fatte and app_mancanti:
                await update.message.reply_text(f"Ok, va bene. Le app restanti le farai con Luca 👍🏻")
                await asyncio.sleep(0.8)
            await update.message.reply_text(f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
        elif is_ambiguous:
            # Claude gestisce
            risposta = await chiedi_claude(state, text, "Hai già fatto qualcuna di queste app?")
            if risposta:
                if "history" not in state: state["history"] = []
                state["history"].append({"lead": text, "bot": risposta})
                await typing(update)
                await update.message.reply_text(risposta)
            else:
                state["quali_app_risposta"] = text
                state["step"] = "messaggio_finale"
                await typing(update)
                await update.message.reply_text(f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
        return

    # ══════════════════════════════════════════════════════════════
    # STEP 4 — Messaggio finale per Luca
    # ══════════════════════════════════════════════════════════════
    if step == "messaggio_finale":
        domanda_finale = "C'è qualcosa che vorresti far sapere a Luca prima di iniziare?"
        # Controlla se è una domanda o obiezione — passa a Claude
        t_lower = text.strip().lower()
        parole_obiezione = [
            "deposito", "soldi", "investimento", "costo", "pagare", "pagamento",
            "truffa", "sicuro", "legale", "rischio", "fregatura",
            "minorenne", "anni", "documento", "carta",
            "tempo", "quando", "quanto", "come", "perché", "perche",
            "posso", "devo", "serve", "bisogna", "funziona",
            "luca", "chi", "cosa", "dove",
        ]
        is_obiezione = "?" in text or any(kw in t_lower for kw in parole_obiezione)
        if is_obiezione:
            risposta = await chiedi_claude(state, text, domanda_finale)
            if risposta:
                if "history" not in state: state["history"] = []
                state["history"].append({"lead": text, "bot": risposta})
                await typing(update)
                await update.message.reply_text(risposta)
                return
        state["messaggio_preparazione"] = text
        await esegui_fine(update, context, state, user)
        return

# ══════════════════════════════════════════════════════════════════
# HANDLE — delay anti-doppio
# ══════════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in pending_messages:
        try: pending_messages[user_id].cancel()
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
# COMANDI
# ══════════════════════════════════════════════════════════════════

async def riprendi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(LUCA_CHAT_ID): return
    args = context.args
    if not args:
        await update.message.reply_text("Usi:\n/riprendi [user_id] → report + foglio\n/riprendi [user_id] \"testo\" → manda messaggio")
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
                await update.message.reply_text(f"✅ Report inviato per ID {target_id}")
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
