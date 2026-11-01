import re, sqlite3, telebot
from datetime import datetime

TOKEN = "9244035884:AAEZ0AZuPbPdURGIU6iRRcysvCjBXST8GyQ"
bot = telebot.TeleBot(TOKEN)

def init_db():
    conn = sqlite3.connect("keuangan.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS transaksi (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        tipe TEXT, 
        kategori TEXT, 
        nominal INTEGER, 
        dompet TEXT, 
        keterangan TEXT, 
        tanggal TEXT
    )""")
    conn.commit()
    conn.close()

def extract_all_nominals(text):
    t = text.lower().replace(".", "").replace(",", "")
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(k|rb|ribu|jt|juta)?", t)
    total = 0
    items_count = 0
    for val_str, unit in matches:
        if not val_str: continue
        v = float(val_str)
        if unit in ["k", "rb", "ribu"]: v *= 1000
        elif unit in ["jt", "juta"]: v *= 1000000
        total += int(v)
        items_count += 1
    return total, items_count

def classify(text):
    t = text.lower()
    dompet = "Cash"
    for w in ["bca", "mandiri", "jago", "gopay", "ovo", "dana", "qris", "spay", "seabank"]:
        if w in t:
            dompet = w.upper()
            break
            
    if any(w in t for w in ["gaji", "bonus", "transfer masuk", "terima"]):
        return "INCOME", "Pemasukan", dompet
        
    kat = "Lain-lain"
    food_words = ["kopi", "kopken", "makan", "nasi", "nasgor", "warteg", "bakso", "roti", "mie", "ayam", "snack", "es", "boba"]
    trans_words = ["bensin", "pertamax", "pertalite", "parkir", "tol", "grab", "gojek", "ojol", "maxim"]
    bill_words = ["wifi", "indihome", "listrik", "pln", "pulsa", "paket data", "kost", "sewa", "air"]
    shop_words = ["belanja", "tokped", "shopee", "baju", "sepatu", "indomaret", "alfamart"]

    if any(w in t for w in food_words):
        kat = "Makanan & Minuman"
    elif any(w in t for w in trans_words):
        kat = "Transportasi"
    elif any(w in t for w in bill_words):
        kat = "Tagihan & Utilitas"
    elif any(w in t for w in shop_words):
        kat = "Belanja"
        
    return "EXPENSE", kat, dompet

@bot.message_handler(commands=["start", "help"])
def welcome(m):
    txt = (
        "⚡️ *BAGIRATA ASSISTANT*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💳 *1. CATAT PENGELUARAN PRIBADI*\n"
        "Ketik teks santai, bisa catat banyak menu sekaligus:\n"
        "• `kopken 25k nasgor 10k bca`\n"
        "• `bensin 50k qris`\n"
        "• `gaji freelance 1.5jt mandiri`\n\n"
        "📊 *2. REKAP SALDO BULANAN*\n"
        "• Ketik `/rekap` untuk melihat sisa uangmu.\n\n"
        "🧾 *3. FITUR SPLIT BILL*\n"
        "• *Bagi Rata Kilat:*\n"
        "  `/split 150k / 3`\n"
        "  `/split 200k / 4 + 10 5` _(pajak 10%, service 5%)_\n"
        "• *Berdasarkan Pesanan:*\n"
        "  `/split 10 5`\n"
        "  `Andi: 40k, 15k`\n"
        "  `Budi: 35k`\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    bot.reply_to(m, txt, parse_mode="Markdown")

@bot.message_handler(commands=["rekap"])
def rekap(m):
    conn = sqlite3.connect("keuangan.db")
    c = conn.cursor()
    bln = datetime.now().strftime("%Y-%m")
    
    c.execute("SELECT tipe, SUM(nominal) FROM transaksi WHERE tanggal LIKE ? GROUP BY tipe", (f"{bln}%",))
    tot = dict(c.fetchall())
    
    c.execute("SELECT kategori, SUM(nominal) FROM transaksi WHERE tipe='EXPENSE' AND tanggal LIKE ? GROUP BY kategori ORDER BY SUM(nominal) DESC", (f"{bln}%",))
    breakdown = c.fetchall()
    conn.close()

    tot_in = tot.get("INCOME", 0)
    tot_out = tot.get("EXPENSE", 0)
    saldo = tot_in - tot_out

    res = (
        f"📊 *REKAP PRIBADI ({datetime.now().strftime('%B %Y')})*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 *Pemasukan*   : Rp {tot_in:,.0f}\n"
        f"🔴 *Pengeluaran* : Rp {tot_out:,.0f}\n"
        "────────────────────\n"
        f"💰 *Sisa Saldo*  : *Rp {saldo:,.0f}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*Rincian Per Kategori:*\n"
    )
    if not breakdown:
        res += "_(Belum ada pengeluaran dicatat)_\n"
    for kat, nom in breakdown:
        res += f"• {kat:<18} : Rp {nom:,.0f}\n"

    bot.reply_to(m, res, parse_mode="Markdown")

@bot.message_handler(commands=["split"])
def split_cmd(m):
    clean_text = m.text.replace("/split", "").strip()
    
    quick = re.search(r"(\d+(?:\.\d+)?\s*(?:k|rb|ribu|jt|juta)?)\s*(?:/|bagi)\s*(\d+)(?:\s*\+\s*([\d\.\s]+))?", clean_text, re.IGNORECASE)
    if quick:
        total_raw, _ = extract_all_nominals(quick.group(1))
        orang = int(quick.group(2))
        extra_str = quick.group(3) or ""
        
        extra_pct = 0.0
        if extra_str:
            for num in extra_str.split():
                if num.replace(".", "").isdigit():
                    extra_pct += float(num)
                    
        total_akhir = round(total_raw * (1 + (extra_pct / 100.0)))
        per_orang = round(total_akhir / orang) if orang > 0 else 0
        
        res = (
            "🧾 *SPLIT BILL (BAGI RATA)*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• Total Tagihan : Rp {total_raw:,.0f}\n"
            f"• Jumlah Orang  : {orang} orang\n"
        )
        if extra_pct > 0:
            res += f"• Ekstra (Tax/Svc): +{extra_pct:.1f}%\n"
            res += f"• Total Akhir   : Rp {total_akhir:,.0f}\n"
        res += (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Tagihan Per Orang:*\n"
            f"👉 *Rp {per_orang:,.0f}*\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        bot.reply_to(m, res, parse_mode="Markdown")
        return

    lines = m.text.strip().split("\n")
    hdr = lines[0].split()
    p, s = 0.0, 0.0
    if len(hdr) >= 2 and hdr[1].replace(".", "").isdigit(): p = float(hdr[1])
    if len(hdr) >= 3 and hdr[2].replace(".", "").isdigit(): s = float(hdr[2])
    
    mul = 1 + ((p + s) / 100.0)
    subtotal_meja = 0
    person_data = {}

    for l in lines[1:]:
        if ":" not in l: continue
        nama, its = l.split(":", 1)
        tot_person, _ = extract_all_nominals(its)
        person_data[nama.strip()] = tot_person
        subtotal_meja += tot_person

    if not person_data:
        bot.reply_to(
            m, 
            "💡 *PANDUAN SPLIT BILL*\n━━━━━━━━━━━━━━━━━━━━\n"
            "1. *Bagi Rata Cepat:*\n"
            "`/split 150k / 3`\n"
            "`/split 150k / 3 + 10 5`\n\n"
            "2. *Rincian Pesanan:*\n"
            "`/split 10 5`\n"
            "`Andi: 40k, 15k`\n"
            "`Budi: 35k`",
            parse_mode="Markdown"
        )
        return

    total_akhir = round(subtotal_meja * mul)
    res = "🧾 *RINCIAN SPLIT BILL*\n━━━━━━━━━━━━━━━━━━━━\n"
    if (p + s) > 0:
        res += f"• Tambahan Biaya: +{p+s:.1f}%\n━━━━━━━━━━━━━━━━━━━━\n\n"
    else:
        res += "• Biaya Bersih (Tanpa Pajak)\n━━━━━━━━━━━━━━━━━━━━\n\n"

    for nama, sub in person_data.items():
        tagihan = round(sub * mul)
        res += f"👤 *{nama}*\n• Pesanan : Rp {sub:,.0f}\n• Tagihan : *Rp {tagihan:,.0f}*\n\n"

    res += f"━━━━━━━━━━━━━━━━━━━━\n💵 *Total Meja : Rp {total_akhir:,.0f}*"
    bot.reply_to(m, res, parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def tx(m):
    if m.text.startswith("/"): return
    total_nom, count = extract_all_nominals(m.text)
    if total_nom == 0:
        bot.reply_to(m, "❌ Nominal tidak terbaca. Contoh: `kopi 25k bca`")
        return
        
    tipe, kat, domp = classify(m.text)
    tgl = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("keuangan.db")
    c = conn.cursor()
    c.execute("INSERT INTO transaksi (user_id, tipe, kategori, nominal, dompet, keterangan, tanggal) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (m.from_user.id, tipe, kat, total_nom, domp, m.text, tgl))
    conn.commit()
    conn.close()

    icon = "🔴" if tipe == "EXPENSE" else "🟢"
    label = "PENGELUARAN PRIBADI" if tipe == "EXPENSE" else "PEMASUKAN PRIBADI"
    
    res = (
        f"{icon} *{label}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• Total Nominal : *Rp {total_nom:,.0f}*" + (f" _({count} item)_" if count > 1 else "") + "\n"
        f"• Kategori      : {kat}\n"
        f"• Sumber Dana   : {domp}\n"
        f"• Rincian       : _{m.text}_\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 {tgl[8:10]}/{tgl[5:7]}/{tgl[:4]} • {tgl[11:16]} WIB"
    )
    bot.reply_to(m, res, parse_mode="Markdown")

init_db()
print(">>> BagiRata Bot Cloud Active! <<<")
bot.infinity_polling()
