import os
import json
import base64
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8789896507:AAFnPz3n761e8tva4u5-OpWjlzBIr_EnN7A"
GEMINI_API_KEY = "AIzaSyCCU5l_b3FBwPTvCKOLIhSfwwkSpzDqiWQ"
GITHUB_TOKEN   = "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"
GITHUB_USER    = "Garzianov"
GITHUB_REPO    = "brand-database"
FILE_PATH      = "src/App.jsx"

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await msg.reply_text("📸 Screen ricevuto! Analisi in corso...")

    # 1. Scarica la foto
    photo = msg.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    image_b64 = base64.b64encode(file_bytes).decode("utf-8")

    # 2. Chiama Gemini Vision
    prompt = """Analizza questo screenshot di un profilo Instagram di un brand.
Rispondi SOLO con un oggetto JSON valido, senza markdown, senza backtick, senza testo aggiuntivo.
Formato esatto:
{"nome":"nome reale del brand","nomeSocial":"username senza @","followers":12500,"luogo":"Citta, Paese","descrizione":"breve descrizione in italiano max 120 caratteri","categoria":"Make-up & Cosmetica"}
Per categoria usa solo uno di questi valori esatti: "Make-up & Cosmetica", "Abbigliamento", "Ristoranti / Bar"
Per followers converti: 10,5 mila = 10500, 1,2M = 1200000"""

    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 300
        }
    }

    try:
        resp = requests.post(gemini_url, json=payload, timeout=30)
        result = resp.json()

        # Gestione errori API
        if "error" in result:
            await msg.reply_text(f"❌ Errore Gemini: {result['error'].get('message', 'Errore sconosciuto')}")
            return

        if "candidates" not in result or not result["candidates"]:
            await msg.reply_text(f"❌ Nessuna risposta da Gemini. Risposta: {str(result)[:200]}")
            return

        raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Pulizia risposta
        raw = raw.replace("```json", "").replace("```", "").strip()
        # Trova il JSON nella risposta
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

        brand = json.loads(raw)

    except json.JSONDecodeError as e:
        await msg.reply_text(f"❌ Errore nel parsing JSON: {e}\nRisposta grezza: {raw[:300]}")
        return
    except Exception as e:
        await msg.reply_text(f"❌ Errore generale: {str(e)[:200]}")
        return

    # 3. Mostra dati estratti
    preview = (
        f"✅ *Dati estratti:*\n\n"
        f"🏷 *Nome:* {brand.get('nome','—')}\n"
        f"📱 *Social:* @{brand.get('nomeSocial','—')}\n"
        f"📍 *Luogo:* {brand.get('luogo','—')}\n"
        f"👥 *Followers:* {brand.get('followers','—')}\n"
        f"🏷 *Categoria:* {brand.get('categoria','—')}\n"
        f"📝 *Descrizione:* {brand.get('descrizione','—')}\n\n"
        f"⏳ Pubblicazione su Vercel..."
    )
    await msg.reply_text(preview, parse_mode="Markdown")

    # 4. Leggi App.jsx da GitHub
    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        get_resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{FILE_PATH}",
            headers=headers, timeout=15
        )
        file_data = get_resp.json()
        current_content = base64.b64decode(file_data["content"].replace("\n","")).decode("utf-8")
        sha = file_data["sha"]
    except Exception as e:
        await msg.reply_text(f"❌ Errore lettura GitHub: {str(e)[:200]}")
        return

    # 5. Trova ultimo id e aggiungi brand
    import re
    ids = [int(m) for m in re.findall(r'id:"(\d+)"', current_content)]
    new_id = str(max(ids) + 1) if ids else "1"

    nome        = brand.get("nome","").replace('"', '\\"').replace("\\", "\\\\")
    nomeSocial  = brand.get("nomeSocial","").replace('"', '\\"').replace("@","")
    luogo       = brand.get("luogo","").replace('"', '\\"')
    followers   = int(brand.get("followers", 0))
    categoria   = brand.get("categoria","Make-up & Cosmetica")
    descrizione = brand.get("descrizione","").replace('"', '\\"')

    new_entry = f'  {{ id:"{new_id}", nome:"{nome}", nomeSocial:"{nomeSocial}", repost:"Sì", luogo:"{luogo}", followers:{followers}, categoria:"{categoria}", descrizione:"{descrizione}" }},\n'

    new_content = re.sub(
        r'(const SEED = \[)([\s\S]*?)(\];)',
        lambda m: m.group(1) + m.group(2) + new_entry + m.group(3),
        current_content
    )

    # 6. Push su GitHub
    try:
        encoded = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
        push_resp = requests.put(
            f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{FILE_PATH}",
            headers=headers,
            json={
                "message": f"Add brand: {nome}",
                "content": encoded,
                "sha": sha
            },
            timeout=15
        )
        if push_resp.status_code in [200, 201]:
            await msg.reply_text(
                f"🎉 *{nome}* aggiunto!\n\n"
                f"👉 https://brand-database.vercel.app\n"
                f"_(visibile tra ~60 secondi)_",
                parse_mode="Markdown"
            )
        else:
            err = push_resp.json().get("message","Errore sconosciuto")
            await msg.reply_text(f"❌ Errore GitHub: {err}")
    except Exception as e:
        await msg.reply_text(f"❌ Errore push GitHub: {str(e)[:200]}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Ciao! Mandami lo screenshot di un profilo Instagram e lo aggiungo automaticamente al database.\n\n"
        "👉 https://brand-database.vercel.app"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))
    print("✅ Bot avviato!")
    app.run_polling()

if __name__ == "__main__":
    main()
