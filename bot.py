import os
import asyncio
import logging
from datetime import datetime
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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "INSERISCI_IL_TOKEN_QUI")
LUCA_CHAT_ID = os.environ.get("LUCA_CHAT_ID", "INSERISCI_IL_TUO_CHAT_ID")
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
        logger.info(f"Lead aggiunto al foglio: {username}")
    except Exception as e:
        logger.error(f"Errore Google Sheets: {e}")

BONUS_LIST = ["REVOLUT", "BBVA", "ISYBANK", "BUDDYBANK", "CREDIT AGRICOLE", "KRAK"]

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

def get_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "state" not in context.user_data:
        context.user_data["state"] = {}
    return context.user_data["state"]

async def typing(update: Update, seconds: float = 1.3):
    await update.message.chat.send_action("typing")
    await asyncio.sleep(seconds)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first_name = user.first_name or user.username or "amico"
    state = get_state(context)
    state.clear()
    state["step"] = "conosce_bonus"
    state["nome"] = first_name
    state["username"] = f"@{user.username}" if user.username else f"ID:{user.id}"
    state["link"] = f"t.me/{user.username}" if user.username else f"ID:{user.id}"
    await typing(update)
    await update.message.reply_text(
        f"Ciao {first_name}, piacere sono Luca! Sai come funzionano i bonus app?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    state = get_state(context)
    step = state.get("step")

    if not step:
        await start(update, context)
        return

    if step == "conosce_bonus":
        await typing(update)
        if is_yes(text):
            state["conosce_bonus_risposta"] = text
            state["conosce_bonus"] = True
            state["step"] = "ha_fatto_app"
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        else:
            state["conosce_bonus_risposta"] = text
            state["conosce_bonus"] = False
            state["step"] = "dopo_spiegazione"
            await update.message.reply_text(
                "Ti spiego, i bonus app sono delle applicazioni gratuite dove se tu ti registri "
                "e fai dei semplici passaggi insieme a me, ci riconoscono dei bonus (soldi o buoni amazon) "
                "che puoi prelevare, spostare e usare. Faremo tutto insieme, passo dopo passo, non è richiesto "
                "alcun deposito o spesa, ti dirò quali app usare e cosa fare. Se ci sei iniziamo."
            )
        return

    if step == "dopo_spiegazione":
        await typing(update)
        if is_yes(text):
            state["step"] = "ha_fatto_app"
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        else:
            await update.message.reply_text("Nessun problema! Se hai domande sono qui 🙌")
            state["step"] = "fine"
        return

    if step == "ha_fatto_app":
        state["ha_fatto_app_risposta"] = text
        state["ha_fatto_app"] = is_yes(text)
        state["step"] = "quali_app"
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
            if "BUDDY" in text_upper and "BUDDYBANK" not in fatte:
                fatte.append("BUDDYBANK")
            if ("AGRICOLE" in text_upper or "CREDIT" in text_upper) and "CREDIT AGRICOLE" not in fatte:
                fatte.append("CREDIT AGRICOLE")
            if "ISYB" in text_upper and "ISYBANK" not in fatte:
                fatte.append("ISYBANK")
            state["app_fatte"] = list(set(fatte)) if fatte else []

        state["step"] = "messaggio_finale"
        nome = state.get("nome", "")
        await typing(update)
        await update.message.reply_text(
            f"Ottimo {nome}! C'è qualcosa che vorresti far sapere a Luca, prima di iniziare?"
        )
        return

    if step == "messaggio_finale":
        state["messaggio_preparazione"] = text

        app_fatte = state.get("app_fatte", [])
        app_mancanti = [a for a in BONUS_LIST if a not in app_fatte]
        fatte_str = ", ".join(app_fatte) if app_fatte else "Nessuna"
        mancanti_str = ", ".join(app_mancanti) if app_mancanti else "Tutte già fatte"

        user_obj = update.effective_user
        if user_obj.username:
            contatto = f"👤 @{user_obj.username} → t.me/{user_obj.username}"
        else:
            contatto = f"👤 Nome: {state.get('nome')} (nessun username) → ID: {user_obj.id}"

        conosce_risposta = state.get("conosce_bonus_risposta", "—")
        ha_fatto_risposta = state.get("ha_fatto_app_risposta", "—")
        quali_risposta = state.get("quali_app_risposta", "—")
        msg_prep = state.get("messaggio_preparazione", "—")

        report = (
            f"🔔 NUOVO LEAD QUALIFICATO\n\n"
            f"{contatto}\n"
            f"──────────────\n"
            f"*Sapeva cos'erano i bonus app?* _\"{conosce_risposta}\"_\n"
            f"-\n"
            f"*Aveva già fatto app in passato?* _\"{ha_fatto_risposta}\"_\n"
            f"-\n"
            f"*✅ App già fatte:* _\"{quali_risposta}\"_\n"
            f"──────────────\n\n"
            f"💬 Messaggio preparazione chat: _\"{msg_prep}\"_"
        )

        try:
            await context.bot.send_message(
                chat_id=LUCA_CHAT_ID,
                text=report,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Errore invio report a Luca: {e}")

        # Aggiungi al Google Sheet
        nome_completo = f"{user_obj.first_name or ''} {user_obj.last_name or ''}".strip()
        username_str = f"@{user_obj.username}" if user_obj.username else f"ID:{user_obj.id}"
        link_str = f"t.me/{user_obj.username}" if user_obj.username else f"ID:{user_obj.id}"
        append_lead_to_sheet(nome_completo, username_str, link_str)

        nome = state.get("nome", "")
        state["step"] = "fine"
        await typing(update)
        await update.message.reply_text(
            f"Ottimo {nome}! Ho passato le tue info a Luca, ti contatterà lui direttamente il prima possibile per farti fare tutto passo dopo passo. Preparati 🔥"
        )
        return

    if step == "fine":
        return

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot avviato ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
