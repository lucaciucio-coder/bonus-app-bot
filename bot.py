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

AFFERMATIVO = {
    "si", "sì", "ok", "okay", "va bene", "vabene", "vai", "certo",
    "sisi", "sì sì", "ok ok", "perfetto", "andiamo", "yes", "yep",
    "dai", "sure", "certo certo", "assolutamente", "esatto",
    "più o meno", "piu o meno", "ne ho sentito parlare", "ho sentito parlare",
    "credo di sì", "credo di si", "penso di sì", "penso di si",
    "più o meno sì", "piu o meno si", "qualcosa so", "so qualcosa",
    "vagamente", "in parte", "pressappoco",
    "qualcuna", "qualcuno", "una o due", "un paio", "alcune",
    "ne ho fatta qualcuna", "ne ho fatto qualcuna", "una", "due",
    "ho fatto", "ne ho fatte", "qualche",
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

def get_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "state" not in context.user_data:
        context.user_data["state"] = {}
    return context.user_data["state"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first_name = user.first_name or user.username or "amico"
    state = get_state(context)
    state.clear()
    state["step"] = "conosce_bonus"
    state["nome"] = first_name
    state["username"] = f"@{user.username}" if user.username else f"ID:{user.id}"
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
        await update.message.reply_text("Ok! Ti mando la lista delle app che faccio fare io.")
        await asyncio.sleep(1.5)
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

        if any(neg in text_lower for neg in ["no", "nessuna", "niente", "mai", "nemmeno"]):
            state["app_fatte"] = []
        elif any(vague in text_lower for vague in ["non ricordo", "non mi ricordo", "quasi tutte", "tutte", "praticamente tutte"]):
            state["app_fatte"] = ["NON RICORDA / QUASI TUTTE"]
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
