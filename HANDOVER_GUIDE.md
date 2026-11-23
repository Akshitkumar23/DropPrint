# 🖨️ DropPrint - Handover Guide

> **Counter Operator & Jan Seva Kendra / Xerox Shop Complete Handbook**  
> Yeh guide shopkeeper ya counter operator ke liye hai jo rozana counter par baithkar prints nikalte hain. Isme Day-1 setup se lekar daily routine, pricing change aur troubleshooting sab kuch simple Hinglish me cover kiya gaya hai.

---

## 1. 🏁 Day-1 Setup (Pehli Baar Setup Kaise Karein)

Naye computer par DropPrint setup karne me sirf **2 minute** lagte hain:

1. **Installation:**
   * Pen drive se **`DropPrint_Setup.exe`** par double click karein.
   * **"Install Now"** par click karein.
   * Setup automatically saari files `C:\DropPrint` me extract kar dega, Desktop par **"🖨️ DropPrint Counter"** ka shortcut bana dega, aur Windows Startup me add kar dega.
2. **Default Printer Check Karein:**
   * Windows Settings me jayein (`Printers & Scanners`).
   * Dukan ka main printer (HP LaserJet, Canon LBP, ya Epson) **"Set as Default"** hona chahiye.
3. **Dashboard Open Karein:**
   * Browser me automatically counter dashboard khul jayega:  
     👉 **`http://localhost:8000/shopkeeper/`**
   * Screen par green badge dikhega: **`🟢 Ready (Online)`**

---

## 2. 🏷️ Counter QR Standee Setup (Glass Par QR Lagana)

Customer ko counter par aate hi kaise pata chalega ki wo phone se print kar sakte hain?

1. Shopkeeper Dashboard ke top-right me **`[🖨️ Print Counter Standee]`** button dabayein.
2. Screen par A4 size ka professional standee poster khul jayega.
3. Apne printer se iska ek A4 printout nikalein.
4. **Laminate Karein:** ₹10 wali plastic sheet me ise laminate karwayen taaki dhool ya paani se kharab na ho.
5. **Counter Par Chipkayen:** Ise counter ke samne glass par ya acrylic stand me laga kar rakh dein.

> **💡 QR Mode Ka Farq Samjhein:**
> * **🌐 Mobile 4G/5G Mode (Default):** Customer apne phone ke Jio / Airtel / Vi mobile internet se scan karke upload karega. *Dukan ka Wi-Fi password share karne ki koi zaroorat nahi hai.*
> * **📶 Shop Wi-Fi Mode (Offline Backup):** Agar kabhi area ka internet band ho jaye, toh dashboard me 'Wi-Fi' tab select karke Wi-Fi wala QR standee laga sakte hain, jo bina internet ke dukan ke router par chalta hai.

---

## 3. ⚡ Daily Counter Operations (Rozana Ka 4-Step Routine)

### Step 1: Subah Dukan Kholne Par (Morning Boot)
* Jaise hi computer ON hoga, DropPrint background me automatically start ho jayega.
* Koi black screen ya command chalane ki zaroorat nahi hai.
* Browser me bas dashboard open karke rakhein: **`http://localhost:8000/shopkeeper/`**

### Step 2: Customer Aane Par (Walk-in Customer Flow)
1. Customer counter par lage QR code ko apne mobile camera, Google Lens, ya Paytm/PhonePe scanner se scan karega.
2. Customer ke phone me instant mobile page khulega (koi app download nahi karni padegi).
3. Customer apna PDF, Aadhaar Card, PAN Card, Photo ya Word resume upload karega.
4. Customer page range select karega (jaise `1-2` ya `All`). Screen par turant exact page count aur rate dikhega.
5. Submit karte hi customer ke mobile screen par **4-digit ka pickup token** dikhega (jaise **`PRN-8C10`**).

### Step 3: Payment & Print Release (Cash Lock Rule)
1. Customer counter par bolega: *"Bhaiya, code PRN-8C10, ₹6 lene hain."*
2. Shopkeeper screen par check karega — token **`PRN-8C10`** queue me sabse upar dikh raha hoga.
3. **⚠️ Golden Rule:** Pehle customer se Cash ya shop ke QR par UPI payment lein.
4. Payment milne ke baad screen par green button **`[✅ Receive Cash & Print]`** dabayein.
5. Printer se bina kisi dialog pop-up ke turant fresh print nikal aayega!

---

## 4. 🔒 60-Second Customer Privacy Guarantee

Aksar customer puchte hain: *"Bhaiya, mera Aadhaar card ya private document aapke computer me save toh nahi rahega?"*

Aap customer ko confidently samjha sakte hain:
* DropPrint me **60-Second Auto-Shredder** laga hua hai.
* Jaise hi print nikalta hai, theek 60 seconds ke andar customer ki file computer ki hard disk se permanently delete ho jati hai.
* Dukan ke PC par customer files ka koi clutter ya risk nahi bachta.

---

## 5. 💰 Rates & Pricing Change Kaise Karein

Agar aapko photocopy ya print ke rate badalne hain (jaise ₹2 ki jagah ₹3 karna ho):

1. Computer me `C:\DropPrint\.env` file par right-click karein aur **"Open with Notepad"** select karein.
2. Yeh lines apni dukan ke hisab se change karein:
   ```env
   # Black & White (B&W) print rate per page (Rupees me)
   PRICE_BW_PER_PAGE=2.0

   # Color print rate per page (Rupees me)
   PRICE_COLOR_PER_PAGE=10.0

   # Dono taraf (Duplex) print par discount per sheet
   DUPLEX_DISCOUNT_PER_SHEET=0.5
   ```
3. File save karein (`Ctrl + S`) aur band kar dein.
4. Desktop par bane **`Stop_DropPrint.bat`** par click karein, phir **`Start_DropPrint.bat`** chalayein. Naye rates turant live ho jayenge.

---

## 6. 🛠️ Field Troubleshooting (Common Problems & 10-Second Fixes)

| Problem | Root Cause | 10-Second Solution |
| :--- | :--- | :--- |
| **Customer bol raha hai QR scan karne par link open nahi ho raha** | Phone ka internet slow hai ya tunnel reconnect ho rahi hai | Dashboard par check karein `Tunnel: Active` dikh raha hai ya nahi. Agar customer ka data nahi chal raha, toh dukan ke Wi-Fi se connect karke 'Wi-Fi QR' scan karayein. |
| **Green button dabaya par printer se page nahi nikla** | Printer OFF hai, cable loose hai, ya paper khatam hai | 1. Printer ki power aur USB cable check karein.<br/>2. Paper tray check karein.<br/>3. Windows me check karein printer 'Offline' toh nahi hai. |
| **Browser galti se close ho gaya** | Window close ho gayi | Desktop par bane **"🖨️ DropPrint Counter"** icon par double click karein, dashboard turant wapas open ho jayega. |
| **System ko restart karna hai** | Koi unexpected glitch | 1. Desktop par **`Stop_DropPrint.bat`** run karein.<br/>2. 3 seconds baad **`Start_DropPrint.bat`** run karein. |
| **Naya printer lagaya hai** | Hardware change | Windows Settings me naye printer ko "Set as Default Printer" kar dein. DropPrint automatically naye printer par print bhejne lagega. |

---

## 7. 📊 End-of-Day Operations (Sham Ko Hisab-Kitab)

* Dashboard ke bottom me **"Daily Ledger"** section me aaj ke total printed pages aur total collection (Cash Collected) dikhti hai.
* Dukan band karte waqt koi file delete karne ki zaroorat nahi hai (sab pehle hi auto-purge ho chuka hota hai).
* Computer ko normally Shutdown kar dein. Agli subah PC on karte hi DropPrint apne aap ready milega.

---

## 📋 Shopkeeper Handover Checklist (Dukan Wale Ko Dene Se Pehle)

Dukan wale ko software hand over karne se pehle ye 5 steps tick karein:

- [ ] `DropPrint_Setup.exe` se setup complete kiya.
- [ ] Dukan ka main printer Windows me "Default Printer" set hai.
- [ ] A4 Counter Standee print karke laminate kiya aur glass par lagaya.
- [ ] Apne mobile (4G/5G) se 1 test file upload karke dekhi.
- [ ] Shopkeeper ke samne 4-digit pickup code dalkar **`[Receive Cash & Print]`** se print nikal kar dikhaya.
