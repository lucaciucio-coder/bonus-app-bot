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

# ─── STORAGE ─────────────────────────────────────────────────────
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

# ─── GOOGLE SHEETS ───────────────────────────────────────────────
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
# CLAUDE API — CERVELLO CENTRALE
# ══════════════════════════════════════════════════════════════════

CLAUDE_SYSTEM = """Sei l'assistente personale di Luca Puleo. Il tuo compito è gestire una conversazione di qualificazione con un lead interessato ai bonus app.

COSA SONO I BONUS APP:
- App gratuite (banche/fintech) che pagano bonus di benvenuto per nuove registrazioni
- Zero investimento richiesto, si parte da 0
- Serve essere maggiorenni con documento d'identità valido (carta d'identità + tessera sanitaria)
- 5-10 minuti per app, spalmabili su più giorni
- Bonus accreditati sull'app in pochi giorni, poi Luca spiega come trasferirli
- Guadagno medio totale: +150€
- Luca guadagna quanto il lead (stessi bonus per invitato e invitante)
- App disponibili: REVOLUT (15€), BBVA (10€), ISYBANK/Intesa SanPaolo (30€ buono Amazon), BUDDYBANK (50€), CREDIT AGRICOLE (50€ buono Amazon), KRAK (10$)
- IsyBank è un'app di Intesa SanPaolo

RISPOSTE STANDARD:
- Domande fiscali/ISEE/sussidi/NASPI/RDC → "Per queste domande informati con il tuo commercialista"
- Dettagli tecnici su singole app → "Ne parlerai con Luca"
- Orari/tempistiche contatto → "Ti contatterà il prima possibile"
- Partita IVA/questioni legali di Luca → "Non posso fornire queste informazioni"
- Quanti soldi ha guadagnato Luca → "Non posso riferire queste informazioni"
- Luca ha una fidanzata/domande personali → rispondi con 😄 e vai avanti
- Revolut/app già aperta in passato → "Non potrai sbloccare quel bonus ma farai le altre"
- App già fatta anni fa e richiusa → "In alcuni casi si può riaprire ma generalmente non otterrai il bonus"
- Minorenne → "Purtroppo no, solo maggiorenni. Puoi usare i documenti di qualcun altro (maggiorenne) con il suo consenso"
- Conto di mio padre/moglie → "Se ha il suo consenso sì. Ne parlerai con Luca"
- Vivo all'estero → "Solo determinati bonus. Ne parlerai con Luca"
- iPhone o Android → "Entrambi"
- Sordo/disabile → "Sì, Luca comunica principalmente per messaggio scritto"
- Posso smettere → "Sì, quando vuoi"
- Luca guadagna di più di me → "No, guadagnate la stessa cifra"
- Perché mi aiuta gratis → "Le app pagano bonus sia a te che a Luca, è nel suo interesse aiutarti"
- Fregato online in passato → "Mi dispiace. Con Luca è diverso, c'è un motivo se aiuta persone da +2 anni"
- Recensioni/feedback → "Entra nel suo canale Telegram o seguilo su Instagram"
- Profilo social Luca → "linktr.ee/lucapuleo"
- Quanto ci vuole per app → "Mediamente 5-10 minuti"
- Posso farlo solo la sera → "Nessun problema, ti organizzi con Luca"
- Serve internet → ovviamente sì, ma non dirlo in modo ovvio
- Documenti altrui → "Con il loro consenso sì, ne parlerai con Luca"
- Dove si scaricano → "App Store o Google Play Store, sono app ufficiali"
- I soldi arrivano davvero → "Sì, i bonus vengono accreditati direttamente sull'app in pochi giorni"
- Ho già revolut ma l'ho chiusa → "In alcuni casi si può riaprire ma generalmente non otterrai il bonus"
- Posso farlo dal computer → "In alcuni casi sì. Ne parlerai con Luca"

FLUSSO DI QUALIFICAZIONE (in ordine):
1. STEP "conosce_bonus": chiedi "Sai come funzionano i bonus app?"
2. STEP "ha_fatto_app": chiedi "Hai già fatto qualche app in passato?"
3. STEP "quali_app": mostra lista app e chiedi "Hai già fatto qualcuna di queste app?"
4. STEP "messaggio_finale": chiedi "C'è qualcosa che vorresti far sapere a Luca prima di iniziare?"
5. STEP "fine": conversazione completata

REGOLE CRITICHE PER IL TUO OUTPUT:
Devi rispondere SOLO con un JSON in questo formato esatto, nient'altro:
{
  "azione": "RISPONDI" | "AVANZA" | "AVANZA_CON_RISPOSTA" | "LISTA_APP" | "FINE" | "PAUSA",
  "risposta": "testo da mandare al lead (se applicabile)",
  "step_successivo": "conosce_bonus" | "ha_fatto_app" | "quali_app" | "messaggio_finale" | "fine",
  "registra": {
    "conosce_bonus": true/false,
    "conosce_bonus_risposta": "testo originale",
    "ha_fatto_app": true/false,
    "ha_fatto_app_risposta": "testo originale",
    "quali_app_risposta": "testo originale",
    "app_fatte": ["REVOLUT", "BBVA", ...]
  }
}

SPIEGAZIONE AZIONI:
- RISPONDI: rispondi alla domanda/obiezione ma rimani nello stesso step
- AVANZA: vai allo step successivo con la risposta standard del bot
- AVANZA_CON_RISPOSTA: prima manda la risposta, poi vai allo step successivo
- LISTA_APP: manda la lista delle app (step quali_app)
- FINE: conversazione completata, manda messaggio finale
- PAUSA: il lead vuole andarsene, chiudi conversazione

Nel campo "registra" metti SOLO i campi che hai nuove informazioni da salvare.
Sii MOLTO preciso nel capire se il lead sta rispondendo alla domanda corrente o facendo un'obiezione."""

async def chiedi_claude(state: dict, user_message: str) -> dict:
    """Claude decide cosa fare con il messaggio del lead"""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        step = state.get("step", "conosce_bonus")
        nome = state.get("nome", "il lead")

        storico = []
        if state.get("conosce_bonus_risposta"):
            storico.append(f"- Bonus app conosciuti: SÌ={state.get('conosce_bonus', False)}, risposta originale: '{state['conosce_bonus_risposta']}'")
        if state.get("ha_fatto_app_risposta"):
            storico.append(f"- App fatte in passato: SÌ={state.get('ha_fatto_app', False)}, risposta originale: '{state['ha_fatto_app_risposta']}'")
        if state.get("quali_app_risposta"):
            storico.append(f"- App già fatte: {state.get('app_fatte', [])}, risposta originale: '{state['quali_app_risposta']}'")

        storico_str = "\n".join(storico) if storico else "Nessuna risposta ancora"

        step_descrizioni = {
            "conosce_bonus": "Devi capire se il lead conosce i bonus app. Se sì → AVANZA a ha_fatto_app. Se no → AVANZA_CON_RISPOSTA con spiegazione e poi ha_fatto_app.",
            "ha_fatto_app": "Devi capire se il lead ha già fatto app bancarie in passato. Qualsiasi risposta affermativa (anche vaga) → LISTA_APP. No → LISTA_APP comunque.",
            "quali_app": "Hai già mandato la lista. Il lead sta dicendo quali app ha già fatto. Registra le app fatte → AVANZA a messaggio_finale.",
            "messaggio_finale": "Il lead sta dando il suo messaggio finale per Luca. Registra tutto → FINE.",
        }

        user_prompt = f"""Il lead si chiama {nome}.
STEP CORRENTE: {step}
COSA FARE IN QUESTO STEP: {step_descrizioni.get(step, "Gestisci la conversazione")}

RISPOSTE GIÀ DATE:
{storico_str}

MESSAGGIO DEL LEAD: "{user_message}"

Rispondi SOLO con il JSON richiesto. Nessun testo extra."""

        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 500,
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
            raw = data["content"][0]["text"].strip()
            # Pulisci eventuali markdown
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)

    except Exception as e:
        logger.error(f"Errore Claude API: {e}")
        return None

# ─── STORAGE FUNZIONI ─────────────────────────────────────────────
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

async def typing(update: Update, seconds: float = 1.3):
    await update.message.chat.send_action("typing")
    await asyncio.sleep(seconds)

async def send_lista_app(update: Update):
    await update.message.reply_text(LISTA_APP_MD, parse_mode="MarkdownV2")

async def send_report(context, state: dict, user_obj, tipo: str = "normale"):
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

async def esegui_fine(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, user):
    """Esegue la sequenza finale: report + sheets + messaggi"""
    nome = state.get("nome", "")
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

# ─── JOB TIMERS ──────────────────────────────────────────────────
async def followup_4h(context: ContextTypes.DEFAULT_TYPE):
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

async def report_24h(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    state_ref = data["state_ref"]
    if state_ref.get("step") == "fine": return
    last = state_ref.get("last_message_time")
    if last and (datetime.now(IT_TZ) - last).total_seconds() < 24 * 3600 - 60: return
    await send_report(context, state_ref, data["user_obj"], tipo="arancione")

# ─── /start ──────────────────────────────────────────────────────
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

# ─── PROCESS MESSAGE ─────────────────────────────────────────────
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

    # ── CLAUDE DECIDE ────────────────────────────────────────────
    decisione = await chiedi_claude(state, text)

    if decisione is None:
        # Claude non disponibile — fallback base
        await typing(update)
        if step == "conosce_bonus":
            await update.message.reply_text("Non ho capito bene 😊 Sai già cosa sono i bonus app? Rispondimi con sì o no!")
        elif step == "ha_fatto_app":
            await update.message.reply_text("Ok! Ti mando la lista delle app disponibili.")
            await asyncio.sleep(1.3)
            await send_lista_app(update)
            state["step"] = "quali_app"
        elif step == "quali_app":
            await update.message.reply_text(f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
            state["step"] = "messaggio_finale"
        elif step == "messaggio_finale":
            state["messaggio_preparazione"] = text
            await esegui_fine(update, context, state, user)
        return

    # ── AGGIORNA STATO CON DATI DA CLAUDE ────────────────────────
    registra = decisione.get("registra", {})
    if "conosce_bonus" in registra:
        state["conosce_bonus"] = registra["conosce_bonus"]
    if "conosce_bonus_risposta" in registra:
        state["conosce_bonus_risposta"] = registra["conosce_bonus_risposta"]
    if "ha_fatto_app" in registra:
        state["ha_fatto_app"] = registra["ha_fatto_app"]
    if "ha_fatto_app_risposta" in registra:
        state["ha_fatto_app_risposta"] = registra["ha_fatto_app_risposta"]
    if "quali_app_risposta" in registra:
        state["quali_app_risposta"] = registra["quali_app_risposta"]
        state["messaggio_preparazione"] = registra["quali_app_risposta"]
    if "app_fatte" in registra:
        state["app_fatte"] = registra["app_fatte"]

    azione = decisione.get("azione", "RISPONDI")
    risposta = decisione.get("risposta", "")
    step_successivo = decisione.get("step_successivo", step)

    # ── ESEGUI AZIONE ────────────────────────────────────────────
    if azione == "PAUSA":
        await typing(update)
        await update.message.reply_text(risposta or f"Capito {nome}! Se cambi idea sono qui 🙌")
        state["step"] = "fine"
        try:
            await context.bot.send_message(
                chat_id=LUCA_CHAT_ID,
                text=f"🔴 LEAD PERSO\n\n👤 {nome} (@{user.username or user_id})\nUltimo messaggio: \"{text}\""
            )
        except: pass
        return

    if azione == "RISPONDI":
        if risposta:
            await typing(update)
            await update.message.reply_text(risposta)
        return

    if azione == "AVANZA":
        state["step"] = step_successivo
        await typing(update)
        if step_successivo == "ha_fatto_app":
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        elif step_successivo == "quali_app":
            await update.message.reply_text("Ok! Ti mando la lista delle app disponibili.")
            await asyncio.sleep(1.3)
            await send_lista_app(update)
        elif step_successivo == "messaggio_finale":
            await update.message.reply_text(f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
        elif step_successivo == "fine":
            await esegui_fine(update, context, state, user)
        return

    if azione == "AVANZA_CON_RISPOSTA":
        if risposta:
            await typing(update)
            await update.message.reply_text(risposta)
        state["step"] = step_successivo
        await asyncio.sleep(1.0)
        await update.message.chat.send_action("typing")
        await asyncio.sleep(1.3)
        if step_successivo == "ha_fatto_app":
            await update.message.reply_text("Hai già fatto qualche app in passato?")
        elif step_successivo == "quali_app":
            await update.message.reply_text("Ok! Ti mando la lista delle app disponibili.")
            await asyncio.sleep(1.3)
            await send_lista_app(update)
        elif step_successivo == "messaggio_finale":
            await update.message.reply_text(f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca prima di iniziare?")
        elif step_successivo == "fine":
            await esegui_fine(update, context, state, user)
        return

    if azione == "LISTA_APP":
        state["step"] = "quali_app"
        if risposta:
            await typing(update)
            await update.message.reply_text(risposta)
            await asyncio.sleep(1.0)
        await update.message.chat.send_action("typing")
        await asyncio.sleep(1.3)
        await send_lista_app(update)
        return

    if azione == "FINE":
        if "messaggio_preparazione" not in state or not state["messaggio_preparazione"]:
            state["messaggio_preparazione"] = text
        await esegui_fine(update, context, state, user)
        return

# ─── HANDLE MESSAGGI con delay anti-doppio ───────────────────────
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

# ─── COMANDI ─────────────────────────────────────────────────────
async def riprendi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(LUCA_CHAT_ID): return
    args = context.args
    if not args:
        await update.message.reply_text("Usi:\n/riprendi [user_id] → manda report e aggiorna foglio\n/riprendi [user_id] \"testo\" → manda testo al lead")
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

# ─── MAIN ────────────────────────────────────────────────────────
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
