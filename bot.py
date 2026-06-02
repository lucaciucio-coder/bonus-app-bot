import os
import asyncio
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "INSERISCI_IL_TOKEN_QUI")
LUCA_CHAT_ID = os.environ.get("LUCA_CHAT_ID", "INSERISCI_IL_TUO_CHAT_ID")

BONUS_LIST = ["REVOLUT", "BBVA", "ISYBANK", "BUDDYBANK", "CREDIT AGRICOLE", "KRAK"]

# ─── STEP 1 & 2 — Risposte affermative ───────────────────────────
AFFERMATIVO = {
    # Classici italiani
    "si", "sì", "ok", "okay", "va bene", "vabene", "vai", "certo",
    "sisi", "sì sì", "ok ok", "perfetto", "andiamo", "dai", "sure",
    "assolutamente", "esatto", "confermo", "affermativo", "già",
    "appunto", "esattamente", "precisamente", "giusto", "corretto",
    "capito", "chiaro", "ho capito", "certamente", "naturalmente",
    "ovviamente", "indubitabilmente", "senza dubbio",
    # Inglese
    "yes", "yep", "yup", "yeah", "roger", "sis", "yessir", "sure",
    "absolutely", "definitely", "of course", "indeed", "affirmative",
    "ok ok", "okok", "oki", "oki doki", "okei", "okey",
    # Parziale / incerto ma positivo
    "più o meno", "piu o meno", "ne ho sentito parlare",
    "ho sentito parlare", "credo di sì", "credo di si",
    "penso di sì", "penso di si", "più o meno sì", "piu o meno si",
    "qualcosa so", "so qualcosa", "vagamente", "in parte",
    "pressappoco", "abbastanza", "quasi", "credo", "penso",
    "ho un idea", "ho una vaga idea", "ne so qualcosa",
    "sì più o meno", "già sentito", "già ne ho sentito",
    "mi sembra di sì", "mi sembra di si", "dovrei sapere",
    "ho visto qualcosa", "ne ho letto", "qualcosa ho capito",
    "mi ricordo qualcosa", "ho una infarinatura", "un po", "un poco",
    "tipo sì", "tipo si", "praticamente sì", "praticamente si",
    "direi di sì", "direi di si", "suppongo di sì", "suppongo di si",
    "immagino di sì", "immagino di si", "credo proprio di sì",
    "credo proprio di si", "sì dai", "si dai", "ma sì", "ma si",
    "eh sì", "eh si", "boh sì", "boh si", "sì certo", "si certo",
    "sì ok", "si ok", "sì vai", "si vai", "sì dai", "si dai",
    "more or less", "kind of", "sort of", "i think so", "i guess",
    "mi pare di sì", "mi pare di si", "mi sembra", "potrei dire di sì",
    "penso proprio", "all incirca", "grossomodo", "in linea di massima",
    "sostanzialmente sì", "sostanzialmente si", "fondamentalmente sì",
    "fondamentalmente si", "nella sostanza sì", "nella sostanza si",
    "direi sì", "direi si", "oserei dire sì", "oserei dire si",
    # Entusiasmo
    "certo che sì", "certo che si", "assolutamente sì", "assolutamente si",
    "ma certo", "ma sì", "ma si", "ovvio", "ovviamente sì", "ovviamente si",
    "chiaramente", "chiaramente sì", "chiaramente si",
    "senza dubbio sì", "senza dubbio si", "eccome", "eccome sì",
    "figurati", "figurati sì", "certo certo", "sisi certo",
    "sì sì certo", "ok certo", "ok vai", "ok andiamo",
    "sì andiamo", "si andiamo", "dai andiamo", "forza",
    "forza vai", "pronti", "ci sono", "ci sono sì", "presente",
    "son qui", "sono qui", "son pronto", "sono pronto",
    "son pronta", "sono pronta", "sono dentro", "son dentro",
    "ci sto", "ci sto sì", "mi interessa", "mi interessa sì",
    "voglio provare", "voglio farlo", "voglio farcela",
    "voglio iniziare", "partiamo", "iniziamo", "si parte",
    "si inizia", "facciamo", "facciamolo", "proviamo",
    "proviamoci", "tentiamo", "tentiamoci",
    # Conferme brevi
    "sì.", "si.", "ok.", "okay.", "certo.", "esatto.", "giusto.",
    "yep.", "yes.", "yeah.", "sure.", "dai.", "vai.",
    "👍", "✅", "☑️", "💪", "🔥",
    # Slang / giovanile
    "siuro", "siurissimo", "sisi", "sissì", "sissi",
    "senz altro", "senz'altro", "bello sì", "bello si",
    "ma bello sì", "ma bello si", "top", "top sì", "top si",
    # Per step 2 (ha già fatto app)
    "qualcuna", "qualcuno", "una o due", "un paio", "alcune",
    "ne ho fatta qualcuna", "ne ho fatto qualcuna",
    "ho fatto", "ne ho fatte", "ho già fatto", "già fatto",
    "già fatta", "l ho già fatta", "l ho già fatto",
    "ho già l account", "ho già il conto", "ho esperienza",
    "ho già esperienza", "ho già provato", "già provato",
    "qualcosa ho fatto", "ne ho fatta una", "ne ho fatte due",
    "ne ho fatte alcune", "ne ho fatte un po",
    "ho già un po di esperienza", "qualcosa ho già fatto",
    "ho provato qualcosa", "ho già iniziato con qualcosa",
    "un paio le ho fatte", "qualcuna sì", "alcune sì",
    "ne ho fatta una sola", "ne ho fatte tre o quattro",
    "già ci ho messo mano", "già le conosco",
    "sì ma non tutte", "alcune le ho già fatte",
    "ho già fatto qualche app simile", "ho già fatto roba simile",
    "ho già fatto roba del genere", "conosco il meccanismo",
    "so come funziona", "so già come funziona",
    "ho già idea di come funziona", "ne so già qualcosa",
    "ce l ho già revolut", "ce l ho già bbva",
    "ho già revolut", "ho già bbva", "ho già buddy",
    "ho già krak", "ho già isybank",
    "sì tipo buddy", "sì tipo revolut", "sì tipo krak",
    "tipo revolut", "tipo bbva", "tipo buddy",
    "ho fatto revolut", "ho fatto bbva", "ho fatto buddy",
    "ho fatto isybank", "ho fatto krak", "ho fatto credit agricole",
    "revolut sì", "bbva sì", "buddy sì", "krak sì",
    "revolut si", "bbva si", "buddy si", "krak si",
    "sì alcune", "yes qualcuna", "yep qualcuna",
    "ne conosco qualcuna", "ne ho già usata qualcuna",
    "ho già l account su revolut", "ho già l account su bbva",
    "già registrato", "già registrata", "mi sono già registrato",
    "mi sono già registrata", "ho già un profilo",
    "ho già fatto la registrazione", "l ho già scaricata",
    "l ho già installata", "ce l ho già sul telefono",
    # Risposte con numero
    "1", "2", "3", "4", "5", "una", "due", "tre", "quattro", "cinque",
    "solo una", "solo due", "solo tre", "ne ho fatta solo una",
    "ne ho fatte solo due", "ne ho fatte solo tre",
    # Risposte lunghe affermative
    "sì le conosco già", "sì ho già fatto qualcosa del genere",
    "sì ne ho già fatte alcune in passato",
    "sì ho già avuto esperienze simili",
    "sì mi sono già cimentato con qualcosa del genere",
    "sì ho già preso qualche bonus in passato",
    "sì ho già usato app di questo tipo",
    "sì ho già guadagnato qualcosa con le app",
    "sì conosco il meccanismo dei bonus app",
    "sì ho già sentito di questi bonus",
    "sì un mio amico me ne ha parlato",
    "sì ho visto sui social",
    "sì ne ho letto online",
    "sì ho già provato qualcosa di simile",
    "sì mi sembra di averlo già visto",
    "sì ricordo di aver sentito qualcosa",
    "sì me lo ricordo vagamente",
    "sì più o meno so come funziona",
    "sì ho una vaga idea",
    "sì mi ricordo qualcosa",
}

# ─── STEP 3 — Negazioni ──────────────────────────────────────────
NEGATIVO = {
    "no", "nope", "nein", "non", "nada", "niente", "nessuna",
    "nessuno", "mai", "nemmeno", "neanche", "neppure",
    "assolutamente no", "per niente", "proprio no",
    "no davvero", "no veramente", "no mai", "no nessuna",
    "no niente", "non ne ho fatta nessuna", "non ne ho fatto nessuna",
    "non ne ho fatta nemmeno una", "non ne ho fatto nemmeno uno",
    "non le conosco", "non le ho mai fatte", "non ho mai fatto",
    "non ho mai usato", "non ho mai provato", "non ci ho mai provato",
    "non sapevo nemmeno esistessero", "non ne sapevo niente",
    "non ne ero a conoscenza", "non ne avevo mai sentito parlare",
    "non le ho mai sentite", "non le conosco affatto",
    "non ne ho idea", "non sapevo esistessero",
    "zero", "zero esperienze", "zero app", "nulla",
    "nulla di tutto questo", "nessuna di queste",
    "nessuna purtroppo", "nessuna ahimè", "nessuna ancora",
    "ancora nessuna", "ancora niente", "per ora nessuna",
    "per ora niente", "non ancora", "non ancora nessuna",
    "n", "no.", "nope.", "nah", "nah nah", "na",
    "proprio nessuna", "nemmeno una", "neanche una",
    "non ho fatto niente del genere", "non ho mai fatto niente del genere",
    "non conosco nessuna di queste app",
    "non ne ho mai sentito parlare di nessuna",
    "non mi sono mai registrato su nessuna",
    "non mi sono mai registrata su nessuna",
    "non ho account su nessuna di queste",
    "non ho profili su nessuna",
    "non ho mai scaricato nessuna di queste",
    "non ho mai installato nessuna di queste",
    "niente di niente", "zero assoluto", "proprio zero",
    "davvero nessuna", "veramente nessuna",
}

# ─── STEP 3 — Risposte vaghe ─────────────────────────────────────
VAGO = {
    "non ricordo", "non mi ricordo", "non ricordo bene",
    "non mi ricordo bene", "non ricordo più", "non mi ricordo più",
    "non ricordo quale", "non mi ricordo quale",
    "quasi tutte", "tutte", "praticamente tutte", "tutte quante",
    "più o meno tutte", "quasi tutte quante",
    "boh", "mah", "boh non saprei", "mah non saprei",
    "non saprei", "non lo so", "non so",
    "forse", "forse qualcuna", "forse una", "forse due",
    "non sono sicuro", "non sono sicura",
    "non sono certo", "non sono certa",
    "mi sembra", "mi pare", "credo", "penso",
    "dovrei avere", "potrei avere", "mi sembra di aver fatto",
    "mi pare di aver fatto", "credo di aver fatto",
    "penso di aver fatto", "non ricordo se",
    "non mi ricordo se", "non so se",
    "forse revolut", "forse bbva", "forse buddy",
    "forse isybank", "forse krak", "forse credit agricole",
    "mi sembra revolut", "mi sembra bbva", "mi sembra buddy",
    "credo revolut", "credo bbva", "credo buddy",
    "penso revolut", "penso bbva", "penso buddy",
    "dovrei avere revolut", "dovrei avere bbva",
    "potrei avere revolut", "potrei avere bbva",
    "non ricordo il nome", "non mi ricordo il nome",
    "non ricordo i nomi", "non mi ricordo i nomi",
    "qualcuna ma non ricordo quale", "una o due ma non ricordo",
    "alcune ma non ricordo quali", "qualcosa ma non ricordo",
    "mi sembra di averne fatta qualcuna",
    "credo di averne fatta qualcuna",
    "penso di averne fatte alcune",
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

async def typing(update: Update, seconds: float = 1.8):
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
            state["conosce_bonus"] = True
            state["step"] = "ha_fatto_app"
            await update.message.reply_text("Ottimo, hai già fatto qualche app in passato?")
        else:
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
        state["ha_fatto_app"] = is_yes(text)
        state["step"] = "quali_app"
        await typing(update)
        await update.message.reply_text("Ok! Ti mando la lista delle app che faccio fare io.")
        await update.message.chat.send_action("typing")
        await asyncio.sleep(1.8)
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
        text_upper = text.upper()
        text_lower = text.lower()

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

        app_fatte = state.get("app_fatte", [])
        app_mancanti = [a for a in BONUS_LIST if a not in app_fatte]

        conosce = "✅ Sì" if state.get("conosce_bonus") else "❌ No"
        ha_fatto = "✅ Sì" if state.get("ha_fatto_app") else "❌ No"
        fatte_str = ", ".join(app_fatte) if app_fatte else "Nessuna"
        mancanti_str = ", ".join(app_mancanti) if app_mancanti else "Tutte già fatte"

        user_obj = update.effective_user
        if user_obj.username:
            contatto = f"👤 @{user_obj.username} → t.me/{user_obj.username}"
        else:
            contatto = f"👤 Nome: {state.get('nome')} (nessun username) → ID: {user_obj.id}"

        report = (
            f"🔔 NUOVO LEAD QUALIFICATO\n\n"
            f"{contatto}\n"
            f"──────────────\n"
            f"🧠 Sapeva cos'erano i bonus app? {conosce}\n"
            f"📱 Aveva già fatto app in passato? {ha_fatto}\n"
            f"✅ App già fatte: {fatte_str}\n"
            f"⏳ App mancanti (da fare): {mancanti_str}\n"
            f"──────────────\n\n"
            f"💬 Messaggio finale lead: \"{text}\""
        )

        try:
            await context.bot.send_message(chat_id=LUCA_CHAT_ID, text=report)
        except Exception as e:
            logger.error(f"Errore invio report a Luca: {e}")

        await typing(update)
        nome = state.get("nome", "")
        state["step"] = "fine"
        await update.message.reply_text(
            f"Ottimo {nome}! Ho passato le tue info a Luca, ti contatterà lui direttamente il prima possibile per farti fare tutto passo dopo passo. Tieni gli occhi aperti 🚀"
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
