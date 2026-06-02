import os
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

# ─── CONFIGURA QUI ───────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "INSERISCI_IL_TOKEN_QUI")
LUCA_CHAT_ID = os.environ.get("LUCA_CHAT_ID", "INSERISCI_IL_TUO_CHAT_ID")
# ─────────────────────────────────────────────────────────────────

BONUS_LIST = ["REVOLUT", "BBVA", "ISYBANK", "BUDDYBANK", "CREDIT AGRICOLE", "KRAK"]

AFFERMATIVO = {
    "si", "sì", "ok", "okay", "va bene", "vabene", "vai", "certo",
    "sisi", "sì sì", "ok ok", "perfetto", "andiamo", "yes", "yep",
    "dai", "sure", "certo certo", "assolutamente", "esatto"
}

def is_yes(text: str) -> bool:
    t = text.strip().lower()
    if t in AFFERMATIVO:
        return True
    for kw in AFFERMATIVO:
        if kw in t:
            return True
    return False

def get_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "state" not in context.user_data:
        context.user_data["state"] = {}
    return context.user_data["state"]

# ── /start ────────────────────────────────────────────────────────
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

# ── GESTIONE MESSAGGI ─────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    state = get_state(context)
    step = state.get("step")

    # Se non ha ancora fatto /start
    if not step:
        await start(update, context)
        return

    # STEP 1 — Sa come funzionano i bonus app?
    if step == "conosce_bonus":
        if is_yes(text):
            state["conosce_bonus"] = True
            state["step"] = "ha_fatto_app"
            await update.message.reply_text(
                "Ottimo, hai già fatto qualche app in passato?"
            )
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

    # STEP 2a — Dopo la spiegazione: vuole procedere?
    if step == "dopo_spiegazione":
        if is_yes(text):
            state["step"] = "ha_fatto_app"
            await update.message.reply_text(
                "Ottimo, hai già fatto qualche app in passato?"
            )
        else:
            await update.message.reply_text(
                "Nessun problema! Se hai domande sono qui 🙌"
            )
            state["step"] = "fine"
        return

    # STEP 2b — Ha già fatto app?
    if step == "ha_fatto_app":
        if is_yes(text):
            state["ha_fatto_app"] = True
        else:
            state["ha_fatto_app"] = False

        state["step"] = "quali_app"
        await update.message.reply_text("Ok! Ti mando la lista delle app che faccio fare io.")
        await update.message.reply_text(
            "BONUS ATTIVI\n\n"
            "REVOLUT - 15€\n"
            "BBVA - 10€\n"
            "ISYBANK - 30€ BUONO AMAZON\n"
            "BUDDYBANK - 50€\n"
            "CREDIT AGRICOLE - 50€ BUONO AMAZON\n"
            "KRAK - 10$\n\n"
            "Hai già fatto qualcuna di queste app?"
        )
        return

    # STEP 3 — Quali app ha già fatto?
    if step == "quali_app":
        text_upper = text.upper()

        if any(neg in text.lower() for neg in ["no", "nessuna", "niente", "mai"]):
            state["app_fatte"] = []
        else:
            fatte = [app for app in BONUS_LIST if app in text_upper]
            # Gestione alias
            if "BUDDY" in text_upper:
                fatte.append("BUDDYBANK")
            if "AGRICOLE" in text_upper or "CREDIT" in text_upper:
                if "CREDIT AGRICOLE" not in fatte:
                    fatte.append("CREDIT AGRICOLE")
            if "ISYB" in text_upper:
                if "ISYBANK" not in fatte:
                    fatte.append("ISYBANK")
            fatte = list(set(fatte))
            state["app_fatte"] = fatte

        app_fatte = state.get("app_fatte", [])
        app_mancanti = [a for a in BONUS_LIST if a not in app_fatte]

        # Report per Luca
        conosce = "✅ Sì" if state.get("conosce_bonus") else "❌ No"
        ha_fatto = "✅ Sì" if state.get("ha_fatto_app") else "❌ No"
        fatte_str = ", ".join(app_fatte) if app_fatte else "Nessuna"
        mancanti_str = ", ".join(app_mancanti) if app_mancanti else "Tutte già fatte"

        report = (
            f"🔔 NUOVO LEAD QUALIFICATO\n\n"
            f"👤 Nome: {state.get('nome')}\n"
            f"📲 Username: {state.get('username')}\n\n"
            f"─────────────────────\n"
            f"🧠 Sapeva cos'erano i bonus app? {conosce}\n"
            f"📱 Aveva già fatto app in passato? {ha_fatto}\n"
            f"✅ App già fatte: {fatte_str}\n"
            f"⏳ App mancanti (da fare): {mancanti_str}\n"
            f"─────────────────────\n"
            f"💬 Messaggio finale lead: \"{text}\""
        )

        try:
            await context.bot.send_message(chat_id=LUCA_CHAT_ID, text=report)
        except Exception as e:
            logger.error(f"Errore invio report a Luca: {e}")

        nome = state.get("nome", "")
        state["step"] = "fine"
        await update.message.reply_text(
            f"Ottimo {nome}! Ho passato le tue info a Luca, ti contatterà lui direttamente il prima possibile per farti fare tutto passo dopo passo. Tieniti pronto 🚀"
        )
        return

    # Catch-all — conversazione terminata, non rispondere
    if step == "fine":
        return

# ── MAIN ──────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot avviato ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
