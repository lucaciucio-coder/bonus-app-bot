import os
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    JobQueue,
)
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
LUCA_CHAT_ID = os.environ.get("LUCA_CHAT_ID", "")
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

BONUS_LIST = ["REVOLUT", "BBVA", "ISYBANK", "BUDDYBANK", "CREDIT AGRICOLE", "KRAK"]

# ─── STORICO LEAD ─────────────────────────────────────────────────
lead_history = {}  # {user_id: {"date": ..., "nome": ..., "username": ...}}

# ─── LEAD IN PAUSA (fallback) ─────────────────────────────────────
paused_leads = set()

def append_lead_to_sheet(nome, username, link):
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(GOOGLE_CREDS, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1
        data = datetime.now().strftime("%d/%m/%Y")
        sheet.append_row([data, nome, username, link], value_input_option="USER_ENTERED")
    except Exception as e:
        logger.error(f"Errore Google Sheets: {e}")

# ─── CASISTICHE ───────────────────────────────────────────────────
AFFERMATIVO = {
    "si", "sì", "ok", "okay", "va bene", "vabene", "vai", "certo",
    "sisi", "sì sì", "ok ok", "perfetto", "andiamo", "dai", "sure",
    "assolutamente", "esatto", "confermo", "affermativo", "già",
    "appunto", "esattamente", "precisamente", "giusto", "corretto",
    "capito", "chiaro", "ho capito", "certamente", "naturalmente",
    "ovviamente", "indubitabilmente", "senza dubbio",
    "yes", "yep", "yup", "yeah", "roger", "sis", "yessir",
    "absolutely", "definitely", "of course", "indeed", "affirmative",
    "oki", "oki doki", "okei", "okey", "okok",
    "più o meno", "piu o meno", "ne ho sentito parlare",
    "ho sentito parlare", "credo di sì", "credo di si",
    "penso di sì", "penso di si", "più o meno sì", "piu o meno si",
    "qualcosa so", "so qualcosa", "vagamente", "in parte",
    "pressappoco", "abbastanza", "quasi", "credo", "penso",
    "ho un idea", "ho una vaga idea", "ne so qualcosa",
    "sì più o meno", "già sentito", "già ne ho sentito",
    "mi sembra di sì", "mi sembra di si", "dovrei sapere",
    "ho visto qualcosa", "ne ho letto", "qualcosa ho capito",
    "mi ricordo qualcosa", "un po", "un poco",
    "tipo sì", "tipo si", "praticamente sì", "praticamente si",
    "direi di sì", "direi di si", "suppongo di sì", "suppongo di si",
    "immagino di sì", "immagino di si", "credo proprio di sì",
    "credo proprio di si", "sì dai", "si dai", "ma sì", "ma si",
    "eh sì", "eh si", "boh sì", "boh si", "sì certo", "si certo",
    "sì ok", "si ok", "sì vai", "si vai",
    "more or less", "kind of", "sort of", "i think so", "i guess",
    "mi pare di sì", "mi pare di si", "mi sembra", "potrei dire di sì",
    "penso proprio", "grossomodo", "in linea di massima",
    "sostanzialmente sì", "sostanzialmente si", "fondamentalmente sì",
    "fondamentalmente si", "direi sì", "direi si",
    "certo che sì", "certo che si", "assolutamente sì", "assolutamente si",
    "ma certo", "ovvio", "ovviamente sì", "ovviamente si",
    "chiaramente", "senza dubbio sì", "senza dubbio si",
    "eccome", "figurati", "certo certo", "sisi certo", "sì sì certo",
    "ok certo", "ok vai", "ok andiamo", "sì andiamo", "si andiamo",
    "dai andiamo", "forza", "pronti", "ci sono", "presente",
    "son qui", "sono qui", "ci sto", "mi interessa",
    "voglio provare", "voglio farlo", "voglio iniziare",
    "partiamo", "iniziamo", "si parte", "facciamo", "facciamolo",
    "proviamo", "proviamoci",
    "👍", "✅", "☑️", "💪", "🔥",
    "siuro", "siurissimo", "top",
    "qualcuna", "qualcuno", "una o due", "un paio", "alcune",
    "ne ho fatta qualcuna", "ne ho fatto qualcuna",
    "ho fatto", "ne ho fatte", "ho già fatto", "già fatto",
    "già fatta", "ho esperienza", "ho già esperienza",
    "ho già provato", "già provato", "qualcosa ho fatto",
    "ne ho fatta una", "ne ho fatte due", "ne ho fatte alcune",
    "ho già revolut", "ho già bbva", "ho già buddy",
    "ho già krak", "ho già isybank",
    "tipo revolut", "tipo bbva", "tipo buddy",
    "ho fatto revolut", "ho fatto bbva", "ho fatto buddy",
    "ho fatto isybank", "ho fatto krak", "ho fatto credit agricole",
    "revolut sì", "bbva sì", "buddy sì", "krak sì",
    "revolut si", "bbva si", "buddy si", "krak si",
    "ne conosco qualcuna", "ne ho già usata qualcuna",
    "già registrato", "già registrata", "ho già un profilo",
    "1", "2", "3", "4", "5", "una", "due", "tre", "quattro", "cinque",
    "solo una", "solo due", "ne ho fatta solo una",
    "sì le conosco già", "sì ho già fatto qualcosa del genere",
    "sì ho già avuto esperienze simili",
    "sì ho già preso qualche bonus in passato",
    "sì ho già usato app di questo tipo",
    "sì conosco il meccanismo dei bonus app",
    "sì ho già sentito di questi bonus",
    "sì un mio amico me ne ha parlato",
    "sì ho visto sui social", "sì ne ho letto online",
    "sì ho già provato qualcosa di simile",
    "sì più o meno so come funziona",
}

NEGATIVO = {
    "no", "nope", "nein", "non", "nada", "niente", "nessuna",
    "nessuno", "mai", "nemmeno", "neanche", "neppure",
    "assolutamente no", "per niente", "proprio no",
    "no davvero", "no mai", "no nessuna", "no niente",
    "non ne ho fatta nessuna", "non ne ho fatta nemmeno una",
    "non le conosco", "non le ho mai fatte", "non ho mai fatto",
    "non ho mai usato", "non ho mai provato",
    "non sapevo nemmeno esistessero", "non ne sapevo niente",
    "non ne avevo mai sentito parlare",
    "zero", "zero esperienze", "zero app", "nulla",
    "nessuna di queste", "nessuna purtroppo", "nessuna ancora",
    "ancora nessuna", "ancora niente", "per ora nessuna",
    "non ancora", "nah", "na",
    "non ho fatto niente del genere",
    "non conosco nessuna di queste app",
    "non mi sono mai registrato su nessuna",
    "non mi sono mai registrata su nessuna",
    "niente di niente", "zero assoluto", "davvero nessuna",
}

VAGO = {
    "non ricordo", "non mi ricordo", "non ricordo bene",
    "non mi ricordo bene", "non ricordo più", "non mi ricordo più",
    "quasi tutte", "tutte", "praticamente tutte", "tutte quante",
    "boh", "mah", "boh non saprei", "non saprei", "non lo so",
    "forse", "forse qualcuna", "forse una", "forse due",
    "non sono sicuro", "non sono sicura",
    "mi sembra di aver fatto", "mi pare di aver fatto",
    "credo di aver fatto", "penso di aver fatto",
    "forse revolut", "forse bbva", "forse buddy",
    "forse isybank", "forse krak", "forse credit agricole",
    "mi sembra revolut", "mi sembra bbva", "mi sembra buddy",
    "credo revolut", "credo bbva", "penso revolut",
    "non ricordo il nome", "non mi ricordo il nome",
    "qualcuna ma non ricordo quale", "alcune ma non ricordo quali",
    "non sono sicuro di quale", "non sono sicura di quale",
    "tipo una ma non ricordo", "forse una o due non ricordo",
}

FRUSTRAZIONI = {
    "lascia perdere", "lascia stare", "non mi interessa più",
    "non interessa", "basta", "stop", "smettila", "vai via",
    "non voglio", "non voglio più", "ho cambiato idea",
    "non fa per me", "non è per me", "forget it", "no grazie",
    "non grazie", "arrivederci", "ciao ciao", "bye",
}

DOMANDE_BOT = {
    "sei un bot", "sei un robot", "sei una persona", "sei umano",
    "sei reale", "sei vero", "chi sei", "cosa sei",
    "sei automatico", "parli con me davvero",
    "c'è qualcuno", "c'è una persona", "risponde una persona",
}

DOMANDE_FUNZIONAMENTO = {
    "come funziona", "di cosa si tratta", "cosa è", "cos'è",
    "spiegami", "dimmi di più", "che cosa sono", "cosa sono i bonus",
    "come funzionano i bonus", "spiegami i bonus",
}

DOMANDE_GUADAGNO = {
    "quanto si guadagna", "quanto posso guadagnare", "quanto si fa",
    "quanto posso fare", "quanto si prende", "quanti soldi",
    "quanto guadagni", "quanto fanno", "quanto rendono",
    "è conveniente", "vale la pena",
}

DOMANDE_FIDUCIA = {
    "è una truffa", "sembra una truffa", "non mi fido",
    "è sicuro", "è legale", "ci sono rischi", "è affidabile",
    "funziona davvero", "è vero", "mi fido",
    "non è una truffa", "garanzie", "prove",
}

DOMANDE_GIA_SENTITO = {
    "l'ho già sentito", "ho già sentito", "solita storia",
    "ho già provato robe simili", "già visto", "già sentito",
    "è come gli altri", "come tutte le altre cose",
}

DOMANDE_MOGLIE_PARTNER = {
    "devo chiedere", "lo dico a mia moglie", "lo dico al mio ragazzo",
    "lo dico alla mia ragazza", "lo dico ai miei genitori",
    "prima lo dico a", "ne parlo con",
}

OBIEZIONI_TEMPO = {
    "non ho tempo", "ho poco tempo", "sono occupato", "sono impegnato",
    "non riesco", "non ho modo", "troppo impegnato", "non ho spazio",
    "sono sempre occupato", "lavoro tanto",
}

OBIEZIONI_PENSIERO = {
    "ci penso", "magari dopo", "forse più avanti", "ci devo pensare",
    "vediamo", "non ora", "più tardi", "dopo", "in seguito",
    "fammi pensare", "devo pensarci",
}

OBIEZIONI_SOLDI = {
    "non ho soldi", "non ho budget", "costa qualcosa", "quanto costa",
    "ci vogliono soldi", "non posso permettermi", "sono al verde",
    "non ho disponibilità", "ho pochi soldi",
}

OBIEZIONI_DIFFICOLTA = {
    "è complicato", "è difficile", "non sono capace", "non ci riesco",
    "non sono pratico", "non sono bravo con il telefono",
    "non capisco queste cose", "è troppo tecnico",
    "non sono portato", "non so usare le app",
}

OBIEZIONI_GUADAGNO_DUBBIO = {
    "ma guadagno davvero", "funziona davvero", "si guadagna davvero",
    "è vero che si guadagna", "guadagno per forza",
    "quante possibilità ho", "ma davvero funziona",
}

def is_yes(text: str) -> bool:
    t = text.strip().lower()
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

def calcola_punteggio(state: dict) -> tuple:
    punti = 0
    conosce = state.get("conosce_bonus", False)
    ha_fatto = state.get("ha_fatto_app", False)
    app_fatte = state.get("app_fatte", [])
    fallback_count = state.get("fallback_count", 0)

    if conosce:
        punti += 3
    if ha_fatto:
        punti += 3
    if app_fatte and app_fatte != ["NON RICORDA / INCERTO"]:
        punti += min(len(app_fatte), 3)
    if fallback_count == 0:
        punti += 1

    if punti >= 7:
        return punti, "🔥 HOT"
    elif punti >= 4:
        return punti, "🟡 WARM"
    else:
        return punti, "🔵 COLD"

def get_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "state" not in context.user_data:
        context.user_data["state"] = {}
    return context.user_data["state"]

def get_current_question(state: dict) -> str:
    step = state.get("step")
    if step == "conosce_bonus":
        return "Sai come funzionano i bonus app?"
    elif step == "ha_fatto_app":
        return "Ottimo, hai già fatto qualche app in passato?"
    elif step == "quali_app":
        return "Hai già fatto qualcuna di queste app?"
    elif step == "messaggio_finale":
        nome = state.get("nome", "")
        return f"C'è qualcosa che vorresti far sapere a Luca, prima di iniziare?"
    return ""

async def typing(update: Update, seconds: float = 1.3):
    await update.message.chat.send_action("typing")
    await asyncio.sleep(seconds)

async def forward_to_luca(context: ContextTypes.DEFAULT_TYPE, user_obj, text: str):
    try:
        username = f"@{user_obj.username}" if user_obj.username else f"ID:{user_obj.id}"
        nome = user_obj.first_name or username
        await context.bot.send_message(
            chat_id=LUCA_CHAT_ID,
            text=f"💬 {nome} ({username}):\n\"{text}\""
        )
    except Exception as e:
        logger.error(f"Errore forward: {e}")

async def send_report(context: ContextTypes.DEFAULT_TYPE, state: dict, user_obj, tipo: str = "normale"):
    app_fatte = state.get("app_fatte", [])
    app_mancanti = [a for a in BONUS_LIST if a not in app_fatte]
    fatte_str = ", ".join(app_fatte) if app_fatte else "Nessuna"

    if user_obj.username:
        contatto = f"👤 @{user_obj.username} → t.me/{user_obj.username}"
    else:
        contatto = f"👤 Nome: {state.get('nome')} (nessun username) → ID: {user_obj.id}"

    conosce_risposta = state.get("conosce_bonus_risposta", "—")
    ha_fatto_risposta = state.get("ha_fatto_app_risposta", "—")
    quali_risposta = state.get("quali_app_risposta", "—")
    msg_prep = state.get("messaggio_preparazione", "—")
    punteggio, categoria = calcola_punteggio(state)

    if tipo == "normale":
        intestazione = "🔔 NUOVO LEAD QUALIFICATO"
    else:
        intestazione = "🟠 NUOVO LEAD DA CONTATTARE"

    report = (
        f"{intestazione}\n\n"
        f"{contatto}\n"
        f"──────────────\n"
        f"*Sapeva cos'erano i bonus app?* _\"{conosce_risposta}\"_\n"
        f"-\n"
        f"*Aveva già fatto app in passato?* _\"{ha_fatto_risposta}\"_\n"
        f"-\n"
        f"*✅ App già fatte:* _\"{quali_risposta}\"_\n"
        f"──────────────\n\n"
        f"💬 Messaggio preparazione chat: _\"{msg_prep}\"_\n\n"
        f"📊 Punteggio: *{punteggio}/10* — {categoria}"
    )

    try:
        await context.bot.send_message(
            chat_id=LUCA_CHAT_ID,
            text=report,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Errore invio report: {e}")

# ─── JOB: follow-up 4h ───────────────────────────────────────────
async def followup_4h(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    user_id = data["user_id"]
    nome = data["nome"]
    state_ref = data["state_ref"]

    if state_ref.get("step") == "fine" or state_ref.get("step") is None:
        return
    if state_ref.get("last_message_time"):
        elapsed = datetime.now() - state_ref["last_message_time"]
        if elapsed.total_seconds() < 4 * 3600 - 60:
            return

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(1.3)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ciao {nome}, sei ancora lì? Luca ti aspetta 👀"
        )
        state_ref["followup_sent"] = True
    except Exception as e:
        logger.error(f"Errore follow-up 4h: {e}")

# ─── JOB: report 24h ─────────────────────────────────────────────
async def report_24h(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    user_id = data["user_id"]
    state_ref = data["state_ref"]
    user_obj = data["user_obj"]

    if state_ref.get("step") == "fine":
        return
    if state_ref.get("last_message_time"):
        elapsed = datetime.now() - state_ref["last_message_time"]
        if elapsed.total_seconds() < 24 * 3600 - 60:
            return

    await send_report(context, state_ref, user_obj, tipo="arancione")

# ─── /start ──────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or user.username or "amico"
    state = get_state(context)

    # Storico lead
    if user_id in lead_history:
        prev = lead_history[user_id]
        try:
            await context.bot.send_message(
                chat_id=LUCA_CHAT_ID,
                text=f"⚠️ LEAD GIÀ VISTO\n\n👤 {first_name} (@{user.username or user_id}) ha già contattato il bot il {prev['date']}."
            )
        except Exception as e:
            logger.error(f"Errore storico lead: {e}")

    lead_history[user_id] = {
        "date": datetime.now().strftime("%d/%m/%Y"),
        "nome": first_name,
        "username": f"@{user.username}" if user.username else str(user_id)
    }

    state.clear()
    state["step"] = "conosce_bonus"
    state["nome"] = first_name
    state["username"] = f"@{user.username}" if user.username else f"ID:{user.id}"
    state["link"] = f"t.me/{user.username}" if user.username else f"ID:{user.id}"
    state["fallback_count"] = 0
    state["last_message_time"] = datetime.now()
    state["user_obj"] = user

    # Schedula follow-up 4h e report 24h
    job_data = {
        "chat_id": user.id,
        "user_id": user_id,
        "nome": first_name,
        "state_ref": state,
        "user_obj": user
    }
    context.job_queue.run_once(followup_4h, 4 * 3600, data=job_data, name=f"followup_{user_id}")
    context.job_queue.run_once(report_24h, 24 * 3600, data=job_data, name=f"report24_{user_id}")

    await typing(update)
    await update.message.reply_text(
        f"Ciao {first_name}! 👋 Sono l'assistente personale di Luca Puleo — lui mi ha messo qui per conoscerti un po' prima di contattarti direttamente.\n\n"
        f"Ti faccio solo 3 domande veloci, ci vorrà meno di 2 minuti ⚡\n"
        f"Luca legge tutto quello che scrivi qui e ti contatterà in persona non appena avrò passato le tue info.\n\n"
        f"Partiamo: sai come funzionano i bonus app?"
    )

# ─── /riprendi ───────────────────────────────────────────────────
async def riprendi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    state = get_state(context)

    if user_id in paused_leads:
        paused_leads.discard(user_id)
        domanda = get_current_question(state)
        await typing(update)
        await update.message.reply_text(
            f"✅ Ripreso! Riparto da dove ci eravamo fermati:\n\n{domanda}"
        )
        try:
            await context.bot.send_message(
                chat_id=LUCA_CHAT_ID,
                text=f"✅ Bot ripreso per {state.get('nome')} (@{user.username or user_id})"
            )
        except:
            pass
    else:
        await update.message.reply_text("Nessuna conversazione in pausa al momento.")

# ─── HANDLE MESSAGGI ─────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    user = update.effective_user
    user_id = user.id
    state = get_state(context)
    step = state.get("step")

    # Aggiorna ultimo messaggio
    state["last_message_time"] = datetime.now()

    # Forward a Luca
    await forward_to_luca(context, user, text)

    # Se in pausa aspetta /riprendi
    if user_id in paused_leads:
        return

    # Se non ha fatto /start
    if not step:
        await start(update, context)
        return

    # Se conversazione finita
    if step == "fine":
        return

    t = text.strip().lower()
    nome = state.get("nome", "")

    # ── GESTIONE FRUSTRAZIONE ────────────────────────────────────
    if check_set(text, FRUSTRAZIONI):
        await typing(update)
        await update.message.reply_text(
            f"Capito {nome}, se cambi idea sono qui 🙌"
        )
        state["step"] = "fine"
        try:
            await context.bot.send_message(
                chat_id=LUCA_CHAT_ID,
                text=f"🔴 LEAD PERSO\n\n👤 {nome} (@{user.username or user_id}) ha abbandonato la conversazione.\nUltimo messaggio: \"{text}\""
            )
        except:
            pass
        return

    # ── GESTIONE DOMANDE FUORI FLUSSO ────────────────────────────
    domanda_corrente = get_current_question(state)

    if check_set(text, DOMANDE_BOT):
        await typing(update)
        await update.message.reply_text(
            f"Sono l'assistente virtuale di Luca! Lui legge tutto e ti contatterà di persona 🤝 Torniamo a noi:\n\n{domanda_corrente}"
        )
        return

    if check_set(text, DOMANDE_FUNZIONAMENTO):
        await typing(update)
        await update.message.reply_text(
            "Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri "
            "e fai dei semplici passaggi insieme a me, ci riconoscono dei bonus (soldi o buoni amazon) "
            "che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, non è richiesto "
            f"alcun deposito o spesa, ti dirò quali app usare e cosa fare. Se ci sei iniziamo.\n\n{domanda_corrente}"
        )
        return

    if check_set(text, DOMANDE_GUADAGNO):
        await typing(update)
        await update.message.reply_text(
            "*BONUS ATTIVI*\n\n"
            "*__REVOLUT__*\n15€\n\n"
            "*__BBVA__*\n10€\n\n"
            "*__ISYBANK__*\n30€ BUONO AMAZON\n\n"
            "*__BUDDYBANK__*\n50€\n\n"
            "*__CREDIT AGRICOLE__*\n50€ BUONO AMAZON\n\n"
            "*__KRAK__*\n10$\n\n"
            f"{domanda_corrente}",
            parse_mode="MarkdownV2"
        )
        return

    if check_set(text, DOMANDE_FIDUCIA):
        await typing(update)
        await update.message.reply_text(
            f"Ti capisco {nome}, è giusto essere cauti 🙌 Nessun deposito, nessun rischio — sono app ufficiali di banche e servizi finanziari regolamentati. Luca ti mostrerà tutto in trasparenza prima di iniziare qualsiasi cosa.\n\n{domanda_corrente}"
        )
        return

    if check_set(text, DOMANDE_GIA_SENTITO):
        await typing(update)
        await update.message.reply_text(
            f"Capito {nome}! Probabilmente hai visto cose diverse — qui non si vende nulla e non c'è nessun investimento. Luca ti fa vedere esattamente cosa fa lui, numeri alla mano. Poi decidi tu 🔥\n\n{domanda_corrente}"
        )
        return

    if check_set(text, DOMANDE_MOGLIE_PARTNER):
        await typing(update)
        await update.message.reply_text(
            f"Certo {nome}, assolutamente! Quando vuoi Luca può spiegare tutto anche a loro — è molto più chiaro di persona. Ho già passato le tue info 🙌\n\n{domanda_corrente}"
        )
        return

    if check_set(text, OBIEZIONI_TEMPO):
        await typing(update)
        await update.message.reply_text(
            f"Capito {nome}! Il bello è che non serve molto — Luca ti segue passo per passo e ci vogliono letteralmente 10 minuti per iniziare la prima app. Si fa tutto dal telefono, anche in pausa o la sera 📱 Vuoi che Luca ti contatti in un orario che fa per te?\n\n{domanda_corrente}"
        )
        return

    if check_set(text, OBIEZIONI_PENSIERO):
        await typing(update)
        await update.message.reply_text(
            f"Certo {nome}, prenditi il tempo che ti serve! Tieni presente che i bonus hanno disponibilità limitata e cambiano spesso — Luca ti spiegherà tutto quando vi sentite, così decidi con le informazioni giuste 🙌\n\n{domanda_corrente}"
        )
        return

    if check_set(text, OBIEZIONI_SOLDI):
        await typing(update)
        await update.message.reply_text(
            f"Buona notizia {nome} — non serve nessun deposito e nessuna spesa. Le app sono completamente gratuite, ti registri e basta. I bonus te li danno loro a te, non il contrario 💰 Luca ti mostrerà tutto.\n\n{domanda_corrente}"
        )
        return

    if check_set(text, OBIEZIONI_DIFFICOLTA):
        await typing(update)
        await update.message.reply_text(
            f"Per niente {nome}! Luca ti segue passo per passo, una app alla volta. Non serve saper fare nulla di tecnico — se sai usare il telefono, sai fare questo 📱 È proprio per questo che c'è lui.\n\n{domanda_corrente}"
        )
        return

    if check_set(text, OBIEZIONI_GUADAGNO_DUBBIO):
        await typing(update)
        await update.message.reply_text(
            f"Sì {nome} — Luca lo fa lui stesso e lo fanno già le persone che segue. Te lo mostrerà con i numeri reali quando vi sentite, niente promesse campate in aria 💪\n\n{domanda_corrente}"
        )
        return

    # ── FLUSSO PRINCIPALE ────────────────────────────────────────

    # STEP 1 — Sa come funzionano i bonus app?
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
                "Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri "
                "e fai dei semplici passaggi insieme a me, ci riconoscono dei bonus (soldi o buoni amazon) "
                "che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, non è richiesto "
                "alcun deposito o spesa, ti dirò quali app usare e cosa fare. Se ci sei iniziamo."
            )
        else:
            state["fallback_count"] = state.get("fallback_count", 0) + 1
            if state["fallback_count"] >= 2:
                paused_leads.add(user_id)
                await typing(update)
                await update.message.reply_text(
                    f"Non preoccuparti {nome}, Luca ti contatterà direttamente per spiegarti tutto 🙌"
                )
                try:
                    await context.bot.send_message(
                        chat_id=LUCA_CHAT_ID,
                        text=f"⚠️ INTERVENTO NECESSARIO\n\n👤 {nome} (@{user.username or user_id}) non riesce a rispondere al flusso.\nUltimo messaggio: \"{text}\"\n\nUsa /riprendi per far ripartire il bot dopo che hai parlato con lui."
                    )
                except:
                    pass
            else:
                await typing(update)
                await update.message.reply_text(
                    f"Non ho capito bene 😊 Sai già cosa sono i bonus app? Rispondimi con sì o no!"
                )
        return

    # STEP 2a — Dopo spiegazione
    if step == "dopo_spiegazione":
        if is_yes(text):
            state["step"] = "ha_fatto_app"
            state["fallback_count"] = 0
            await typing(update)
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        else:
            # Riprende se torna
            state["fallback_count"] = 0
            await typing(update)
            await update.message.reply_text(
                "Nessun problema! Se in futuro vuoi saperne di più, Luca è qui 🙌 Vuoi procedere con le domande?"
            )
            state["step"] = "dopo_spiegazione_attesa"
        return

    if step == "dopo_spiegazione_attesa":
        if is_yes(text):
            state["step"] = "ha_fatto_app"
            state["fallback_count"] = 0
            await typing(update)
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        else:
            await typing(update)
            await update.message.reply_text(f"Capito {nome}! Se cambi idea sono qui 🙌")
            state["step"] = "fine"
        return

    # STEP 2b — Ha già fatto app?
    if step == "ha_fatto_app":
        if is_yes(text) or is_no(text) or is_vague(text):
            state["ha_fatto_app_risposta"] = text
            state["ha_fatto_app"] = is_yes(text)
            state["step"] = "quali_app"
            state["fallback_count"] = 0
            await typing(update)
            await update.message.reply_text("Ok! Ti mando la lista delle app che faccio fare io.")
            await update.message.chat.send_action("typing")
            await asyncio.sleep(1.3)
            await update.message.reply_text(
                "*BONUS ATTIVI*\n\n"
                "*__REVOLUT__*\n15€\n\n"
                "*__BBVA__*\n10€\n\n"
                "*__ISYBANK__*\n30€ BUONO AMAZON\n\n"
                "*__BUDDYBANK__*\n50€\n\n"
                "*__CREDIT AGRICOLE__*\n50€ BUONO AMAZON\n\n"
                "*__KRAK__*\n10$\n\n"
                "Hai già fatto qualcuna di queste app?",
                parse_mode="MarkdownV2"
            )
        else:
            state["fallback_count"] = state.get("fallback_count", 0) + 1
            if state["fallback_count"] >= 2:
                paused_leads.add(user_id)
                await typing(update)
                await update.message.reply_text(
                    f"Non preoccuparti {nome}, Luca ti contatterà direttamente 🙌"
                )
                try:
                    await context.bot.send_message(
                        chat_id=LUCA_CHAT_ID,
                        text=f"⚠️ INTERVENTO NECESSARIO\n\n👤 {nome} (@{user.username or user_id}) non riesce a rispondere al flusso.\nUltimo messaggio: \"{text}\"\n\nUsa /riprendi dopo aver parlato con lui."
                    )
                except:
                    pass
            else:
                await typing(update)
                await update.message.reply_text(
                    f"Non ho capito 😊 Hai già fatto qualche app in passato? Sì o no!"
                )
        return

    # STEP 3 — Quali app ha già fatto?
    if step == "quali_app":
        state["quali_app_risposta"] = text
        text_upper = text.upper()

        if is_no(text):
            state["app_fatte"] = []
        elif is_vague(text):
            state["app_fatte"] = ["NON RICORDA / INCERTO"]
        else:
            fatte = [app for app in BONUS_LIST if app in text_upper]
            if "BUDDY" in text_upper and "BUDDYBANK" not in fatte:
                fatte.append("BUDDYBANK")
            if ("AGRICOLE" in text_upper or "CREDIT" in text_upper) and "CREDIT AGRICOLE" not in fatte:
                fatte.append("CREDIT AGRICOLE")
            if "ISYB" in text_upper and "ISYBANK" not in fatte:
                fatte.append("ISYBANK")
            state["app_fatte"] = list(set(fatte)) if fatte else []

        state["step"] = "messaggio_finale"
        state["fallback_count"] = 0
        await typing(update)
        await update.message.reply_text(
            f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca, prima di iniziare?"
        )
        return

    # STEP 4 — Messaggio finale
    if step == "messaggio_finale":
        state["messaggio_preparazione"] = text
        state["fallback_count"] = 0

        punteggio, categoria = calcola_punteggio(state)

        # Messaggio finale personalizzato per tipo lead
        if categoria == "🔥 HOT":
            msg_finale = f"Ottimo {nome}! Ho passato le tue info a Luca, ti contatterà lui direttamente il prima possibile. Preparati 🔥"
        elif categoria == "🟡 WARM":
            msg_finale = f"Ottimo {nome}! Ho passato le tue info a Luca, ti spiegherà tutto passo per passo — vedrai che è più semplice di quanto pensi 💪"
        else:
            msg_finale = f"Ottimo {nome}! Parti da zero? Ancora meglio — Luca ti seguirà dall'inizio, step by step 🙌"

        # Report a Luca
        await send_report(context, state, user, tipo="normale")

        # Google Sheets
        nome_completo = f"{user.first_name or ''} {user.last_name or ''}".strip()
        username_str = f"@{user.username}" if user.username else f"ID:{user.id}"
        link_str = f"t.me/{user.username}" if user.username else f"ID:{user.id}"
        append_lead_to_sheet(nome_completo, username_str, link_str)

        state["step"] = "fine"
        await typing(update)
        await update.message.reply_text(msg_finale)
        return

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("riprendi", riprendi))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot avviato ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
