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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
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
paused_leads = set()
all_leads = []
orange_leads = []
pending_messages = {}
global_states = {}

LISTA_APP_MD = (
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
- App gratuite (banche/fintech) che pagano bonus per nuove registrazioni
- Zero investimento, si parte da 0
- Serve: maggiorenni, documento identità valido (CI + tessera sanitaria)
- 5-10 min per app, spalmabili su più giorni
- Bonus accreditati in pochi giorni, poi Luca spiega come trasferirli
- Guadagno medio: +150€ totali
- Luca guadagna quanto il lead (stessi bonus)
- App: REVOLUT (15€), BBVA (10€), ISYBANK/Intesa SanPaolo (30€ buono Amazon), BUDDYBANK (50€), CREDIT AGRICOLE (50€ buono Amazon), KRAK (10$)

RISPOSTE FISSE (usale sempre):
- Soldi/investimento → "Assolutamente no! Non è richiesto un investimento, si inizia da 0. Sono app gratuite."
- Deposito/costi → stessa risposta sopra
- Truffa/sicurezza → "Nessun rischio — sono app ufficiali di banche regolamentate."
- Come fa soldi Luca → "Le app pagano bonus sia a te che a Luca — per questo ti aiuta gratis."
- Luca guadagna di più → "No, guadagnate la stessa cifra."
- Quanto tempo ci vuole → "5-10 minuti per app."
- Posso farlo di sera/quando voglio → "Sì, ti organizzi con Luca."
- Minorenne → "Solo maggiorenni. Puoi usare documenti di qualcuno (maggiorenne) con il suo consenso."
- Domande fiscali/ISEE/NASPI/RDC → "Informati con il tuo commercialista."
- Dettagli tecnici app → "Ne parlerai con Luca."
- Quando contatta → "Il prima possibile."
- Recensioni/feedback → "Entra nel canale Telegram o seguilo su Instagram."
- Profilo Luca → "linktr.ee/lucapuleo"
- iPhone/Android → "Entrambi."
- App già aperta → "Non potrai sbloccare quel bonus ma farai le altre."
- Ho già fatto tutte → "Ok! Parlerai con Luca su come procedere."
- Cugino/amico non ha guadagnato → "Con Luca è diverso — +2 anni di esperienza, +400 persone aiutate."
- Domande personali su Luca → 😄 e vai avanti
- Posso smettere → "Sì, quando vuoi."
- Dati personali → "Le credenziali restano a te."

REGOLE:
1. Risposte BREVI — max 2 righe
2. Dopo la risposta, fai UNA sola domanda: quella del flusso corrente
3. Non inventare mai informazioni
4. Tono: amichevole, diretto
5. Rispondi SEMPRE in italiano

Rispondi SOLO con il testo da mandare al lead. Nient'altro."""

async def chiedi_claude(state: dict, text: str, domanda_corrente: str) -> str:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        step = state.get("step", "")
        nome = state.get("nome", "il lead")

        prompt = f"""Il lead si chiama {nome}. Step corrente: {step}.
Domanda che gli abbiamo fatto: "{domanda_corrente}"
Messaggio del lead: "{text}"

Rispondi brevemente e alla fine fai questa domanda: "{domanda_corrente}" """

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
            await update.message.reply_text(
                "Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri "
                "e fai dei semplici passaggi insieme a me, ci riconoscono dei bonus (soldi o buoni amazon) "
                "che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, non è richiesto "
                "alcun deposito o spesa, ti dirò quali app usare e cosa fare. Se ci sei iniziamo."
            )
        else:
            # Claude gestisce — risposta ambigua o domanda
            risposta = await chiedi_claude(state, text, "Sai come funzionano i bonus app?")
            if risposta:
                await typing(update)
                await update.message.reply_text(risposta)
            else:
                await typing(update)
                await update.message.reply_text(
                    "Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri "
                    "e fai dei semplici passaggi insieme a me, ci riconoscono dei bonus (soldi o buoni amazon) "
                    "che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, non è richiesto "
                    "alcun deposito o spesa, ti dirò quali app usare e cosa fare. Se ci sei iniziamo."
                )
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
                await typing(update)
                await update.message.reply_text(risposta)
                # Se la risposta di Claude non include domanda → vai avanti
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
        if is_clear_yes(text) or is_clear_no(text):
            state["ha_fatto_app"] = is_clear_yes(text)
            state["ha_fatto_app_risposta"] = text
            state["step"] = "quali_app"
            await typing(update)
            await update.message.reply_text("Ok! Ti mando la lista delle app disponibili.")
            await asyncio.sleep(1.3)
            await update.message.chat.send_action("typing")
            await asyncio.sleep(1.3)
            await update.message.reply_text(LISTA_APP_MD, parse_mode="MarkdownV2")
        else:
            # Claude gestisce
            risposta = await chiedi_claude(state, text, "Hai già fatto qualche app in passato?")
            if risposta:
                await typing(update)
                await update.message.reply_text(risposta)
            else:
                # Fallback — vai avanti con lista
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
        # Se fa una domanda → Claude risponde prima
        if "?" in text and len(text.split()) > 3:
            risposta = await chiedi_claude(state, text, "C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
            if risposta:
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
